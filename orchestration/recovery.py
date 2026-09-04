"""Crash recovery and stale job management engine for pipeline resilience."""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.config import settings
from database.connection import transaction, get_db_cursor
from database.models import Job, DesignStatus, LovableStatus, VercelStatus, OverallStatus
from database.repository import JobRepository
from utils.timestamps import now_iso
from utils.logger import logger


class CrashRecoveryReport(BaseModel):
    """Detailed summary report of recovered jobs across worker stages."""

    recovered_count: int = 0
    design_recovered_count: int = 0
    lovable_recovered_count: int = 0
    vercel_recovered_count: int = 0
    stale_jobs_detected: int = 0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class CrashRecoveryManager:
    """Detects and reconciles stale or interrupted jobs on application startup."""

    def __init__(
        self,
        repository: Optional[JobRepository] = None,
        stale_timeout_seconds: Optional[float] = None,
    ):
        self.repo = repository or JobRepository()
        self.stale_timeout_seconds = (
            stale_timeout_seconds
            if stale_timeout_seconds is not None
            else settings.stale_job_timeout_seconds
        )

    def detect_stale_jobs(self, threshold_seconds: Optional[float] = None) -> List[Job]:
        """Query jobs currently in transient states that haven't updated within threshold."""
        timeout_sec = threshold_seconds if threshold_seconds is not None else self.stale_timeout_seconds
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=timeout_sec)).isoformat()

        with get_db_cursor(self.repo.db_path) as cursor:
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE overall_status NOT IN ('COMPLETED', 'FAILED')
                  AND updated_at <= ?
                  AND (
                      design_status IN ('ANALYZING', 'SEARCHING', 'EVALUATING')
                      OR lovable_status IN ('PREPARING', 'SUBMITTING', 'GENERATING', 'VERIFYING', 'PUBLISHING', 'GITHUB_SYNCING')
                      OR vercel_status IN ('DEPLOYING', 'VERIFYING')
                  )
                ORDER BY queue_position ASC
                """,
                (cutoff,),
            )
            rows = cursor.fetchall()
            return [self.repo._row_to_job(r) for r in rows]

    def recover_interrupted_jobs(self) -> CrashRecoveryReport:
        """Inspect and safely recover all transient in-flight jobs after restart or crash."""
        now = now_iso()
        report = CrashRecoveryReport()

        with transaction(self.repo.db_path) as cursor:
            # 1. Identify all transient jobs
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE overall_status NOT IN ('COMPLETED', 'FAILED')
                  AND (
                      design_status IN ('ANALYZING', 'SEARCHING', 'EVALUATING')
                      OR lovable_status IN ('PREPARING', 'SUBMITTING', 'GENERATING', 'VERIFYING', 'PUBLISHING', 'GITHUB_SYNCING')
                      OR vercel_status IN ('DEPLOYING', 'VERIFYING')
                  )
                ORDER BY queue_position ASC
                """
            )
            rows = cursor.fetchall()
            report.stale_jobs_detected = len(rows)

            for row in rows:
                job_id = row["id"]
                job_uid = row["job_uid"]
                design_st = row["design_status"]
                lovable_st = row["lovable_status"]
                vercel_st = row["vercel_status"]

                recovered_worker = None
                action_taken = ""

                # --- Case A: Design Worker Owned ---
                if design_st in (
                    DesignStatus.ANALYZING.value,
                    DesignStatus.SEARCHING.value,
                    DesignStatus.EVALUATING.value,
                ):
                    recovered_worker = "design"
                    ref_url = row["design_reference_url"]
                    ref_score = row["design_score"]

                    if ref_url and ref_score:
                        # Design was completed before crash
                        cursor.execute(
                            """
                            UPDATE jobs
                            SET design_status = 'DESIGN_READY',
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (now, job_id),
                        )
                        action_taken = f"Advanced design to DESIGN_READY (found reference {ref_url})"
                    else:
                        cursor.execute(
                            """
                            UPDATE jobs
                            SET design_status = 'DESIGN_QUEUED',
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (now, job_id),
                        )
                        action_taken = "Reset design to DESIGN_QUEUED for fresh research"

                    report.design_recovered_count += 1

                # --- Case B: Lovable Worker Owned ---
                elif lovable_st in (
                    LovableStatus.PREPARING.value,
                    LovableStatus.SUBMITTING.value,
                    LovableStatus.GENERATING.value,
                    LovableStatus.VERIFYING.value,
                    LovableStatus.PUBLISHING.value,
                    LovableStatus.GITHUB_SYNCING.value,
                ):
                    recovered_worker = "lovable"
                    published_url = row["lovable_published_url"]
                    project_id = row["lovable_project_id"]

                    if published_url:
                        cursor.execute(
                            """
                            UPDATE jobs
                            SET lovable_status = 'GITHUB_READY',
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (now, job_id),
                        )
                        action_taken = f"Advanced Lovable to GITHUB_READY (already published at {published_url})"
                    else:
                        # Return to WAITING_FOR_DESIGN while preserving lovable_project_id
                        # This guarantees credit safety so project is reused on retry
                        cursor.execute(
                            """
                            UPDATE jobs
                            SET lovable_status = 'WAITING_FOR_DESIGN',
                                overall_status = 'PENDING',
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (now, job_id),
                        )
                        action_taken = (
                            f"Reset Lovable to WAITING_FOR_DESIGN (preserved project {project_id})"
                            if project_id
                            else "Reset Lovable to WAITING_FOR_DESIGN"
                        )

                    report.lovable_recovered_count += 1

                # --- Case C: Vercel Worker Owned ---
                elif vercel_st in (VercelStatus.DEPLOYING.value, VercelStatus.VERIFYING.value):
                    recovered_worker = "vercel"
                    v_proj = row["vercel_project_id"]
                    v_dep = row["vercel_deployment_id"]

                    # Preserves existing project and deployment ID to prevent duplicates
                    cursor.execute(
                        """
                        UPDATE jobs
                        SET vercel_status = 'VERCEL_QUEUED',
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, job_id),
                    )
                    action_taken = (
                        f"Reset Vercel to VERCEL_QUEUED (preserved project {v_proj}, deployment {v_dep})"
                        if v_dep
                        else "Reset Vercel to VERCEL_QUEUED"
                    )
                    report.vercel_recovered_count += 1

                if recovered_worker:
                    report.recovered_count += 1
                    report.details.append(
                        {
                            "job_id": job_id,
                            "job_uid": job_uid,
                            "worker": recovered_worker,
                            "action": action_taken,
                        }
                    )

                    # Record audit event
                    cursor.execute(
                        """
                        INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, metadata, created_at)
                        VALUES (?, 'CRASH_RECOVERY', ?, ?, ?, ?, ?)
                        """,
                        (
                            job_id,
                            f"{recovered_worker}_interrupted",
                            "RECOVERED",
                            f"Crash Recovery: {action_taken}",
                            f'{{"worker": "{recovered_worker}", "job_uid": "{job_uid}"}}',
                            now,
                        ),
                    )

        if report.recovered_count > 0:
            logger.warning(
                f"Crash Recovery reconciler processed {report.recovered_count} interrupted jobs: "
                f"{report.design_recovered_count} Design, {report.lovable_recovered_count} Lovable, "
                f"{report.vercel_recovered_count} Vercel."
            )
        else:
            logger.info("Crash Recovery: No interrupted or stranded jobs detected.")

        return report
