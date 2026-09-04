"""Repository providing atomic SQLite database operations for jobs and metrics."""

import json
import uuid
from typing import Any, Dict, List, Optional
from database.connection import get_db_cursor, transaction
from database.models import (
    DesignStatus,
    Job,
    JobCreate,
    JobLog,
    LovableStatus,
    OverallStatus,
    PipelineStats,
    VercelStatus,
)
from utils.timestamps import calculate_duration_seconds, now_iso


class JobRepository:
    """Repository handling all database CRUD and atomic state transitions."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    def _row_to_job(self, row) -> Job:
        """Convert a sqlite3.Row to a Job Pydantic model."""
        data = dict(row)
        if isinstance(data.get("input_metadata"), str):
            try:
                data["input_metadata"] = json.loads(data["input_metadata"])
            except Exception:
                data["input_metadata"] = {}
        if isinstance(data.get("design_reference_data"), str) and data["design_reference_data"]:
            try:
                data["design_reference_data"] = json.loads(data["design_reference_data"])
            except Exception:
                pass
        return Job(**data)

    def create_job(self, job_in: JobCreate) -> Job:
        """Insert a new job into the persistent database."""
        now = now_iso()
        job_uid = f"job_{uuid.uuid4().hex[:12]}"
        metadata_json = json.dumps(job_in.input_metadata or {})

        sql = """
        INSERT INTO jobs (
            job_uid, csv_row_index, website_url, input_metadata,
            overall_status, design_status, lovable_status, vercel_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with transaction(self.db_path) as cursor:
            cursor.execute(
                sql,
                (
                    job_uid,
                    job_in.csv_row_index,
                    job_in.website_url,
                    metadata_json,
                    OverallStatus.PENDING.value,
                    DesignStatus.DESIGN_QUEUED.value,
                    LovableStatus.WAITING_FOR_DESIGN.value,
                    VercelStatus.VERCEL_QUEUED.value,
                    now,
                    now,
                ),
            )
            job_id = cursor.lastrowid
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row)

    def get_job(self, job_id: int) -> Optional[Job]:
        """Fetch a job by internal integer ID."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def get_job_by_uid(self, job_uid: str) -> Optional[Job]:
        """Fetch a job by public UID."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute("SELECT * FROM jobs WHERE job_uid = ?", (job_uid,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[OverallStatus] = None,
    ) -> List[Job]:
        """List jobs ordered by CSV row index."""
        with get_db_cursor(self.db_path) as cursor:
            if status:
                cursor.execute(
                    "SELECT * FROM jobs WHERE overall_status = ? ORDER BY csv_row_index ASC LIMIT ? OFFSET ?",
                    (status.value, limit, offset),
                )
            else:
                cursor.execute(
                    "SELECT * FROM jobs ORDER BY csv_row_index ASC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            rows = cursor.fetchall()
            return [self._row_to_job(r) for r in rows]

    def count_jobs(self) -> int:
        """Count total jobs."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute("SELECT COUNT(*) FROM jobs")
            return cursor.fetchone()[0]

    def get_pipeline_stats(self) -> PipelineStats:
        """Calculate real-time pipeline statistics across independent worker stages."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute("SELECT COUNT(*) FROM jobs")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE overall_status = 'PENDING'")
            pending = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE design_status IN ('ANALYZING', 'SEARCHING', 'EVALUATING')"
            )
            design_research = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE design_status = 'DESIGN_READY' AND lovable_status = 'WAITING_FOR_DESIGN'"
            )
            waiting_for_lovable = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM jobs 
                   WHERE lovable_status IN ('PREPARING', 'SUBMITTING', 'GENERATING', 'VERIFYING', 'PUBLISHING', 'PUBLISHED', 'GITHUB_SYNCING')"""
            )
            lovable_processing = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE vercel_status IN ('DEPLOYING', 'VERIFYING')"
            )
            vercel_deployment = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE overall_status = 'COMPLETED'")
            completed = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM jobs 
                   WHERE overall_status = 'FAILED' 
                      OR design_status = 'DESIGN_FAILED' 
                      OR lovable_status = 'FAILED' 
                      OR vercel_status = 'FAILED'"""
            )
            failed = cursor.fetchone()[0]

            return PipelineStats(
                total_jobs=total,
                pending=pending,
                design_research=design_research,
                waiting_for_lovable=waiting_for_lovable,
                lovable_processing=lovable_processing,
                vercel_deployment=vercel_deployment,
                completed=completed,
                failed=failed,
            )

    # ---------------- Worker Atomic Claims ---------------- #

    def claim_next_design_job(self) -> Optional[Job]:
        """Atomically claim the next queued design job (concurrent worker support)."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            # Find candidate job with lowest CSV row index
            cursor.execute(
                """
                SELECT * FROM jobs 
                WHERE overall_status IN ('PENDING', 'PROCESSING')
                  AND design_status = 'DESIGN_QUEUED'
                ORDER BY csv_row_index ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            job_id = row["id"]
            cursor.execute(
                """
                UPDATE jobs 
                SET design_status = 'ANALYZING',
                    overall_status = 'PROCESSING',
                    design_started_at = ?,
                    updated_at = ?
                WHERE id = ? AND design_status = 'DESIGN_QUEUED'
                """,
                (now, now, job_id),
            )
            if cursor.rowcount == 0:
                # Concurrent worker already claimed this job
                return None

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    def is_lovable_worker_busy(self) -> bool:
        """Check if any job is currently active in Lovable generation (concurrency = 1)."""
        active_statuses = (
            LovableStatus.PREPARING.value,
            LovableStatus.SUBMITTING.value,
            LovableStatus.GENERATING.value,
            LovableStatus.VERIFYING.value,
            LovableStatus.PUBLISHING.value,
            LovableStatus.PUBLISHED.value,
            LovableStatus.GITHUB_SYNCING.value,
        )
        placeholders = ",".join(["?"] * len(active_statuses))
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM jobs WHERE lovable_status IN ({placeholders})",
                active_statuses,
            )
            count = cursor.fetchone()[0]
            return count > 0

    def claim_next_lovable_job(self) -> Optional[Job]:
        """Atomically claim the next job for Lovable processing.
        Enforces:
        1. Only ONE Lovable generation active at any time.
        2. Design MUST be DESIGN_READY.
        3. Websites are processed in strict CSV order.
        """
        now = now_iso()
        with transaction(self.db_path) as cursor:
            # First verify mutex: check if any job is currently active in Lovable
            active_statuses = (
                LovableStatus.PREPARING.value,
                LovableStatus.SUBMITTING.value,
                LovableStatus.GENERATING.value,
                LovableStatus.VERIFYING.value,
                LovableStatus.PUBLISHING.value,
                LovableStatus.PUBLISHED.value,
                LovableStatus.GITHUB_SYNCING.value,
            )
            placeholders = ",".join(["?"] * len(active_statuses))
            cursor.execute(
                f"SELECT COUNT(*) FROM jobs WHERE lovable_status IN ({placeholders})",
                active_statuses,
            )
            if cursor.fetchone()[0] > 0:
                # Lovable worker is already busy with another website
                return None

            # Find the next job in CSV order that has DESIGN_READY
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE design_status = 'DESIGN_READY'
                  AND lovable_status = 'WAITING_FOR_DESIGN'
                  AND overall_status != 'PAUSED'
                ORDER BY csv_row_index ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            job_id = row["id"]
            cursor.execute(
                """
                UPDATE jobs
                SET lovable_status = 'PREPARING',
                    overall_status = 'PROCESSING',
                    lovable_started_at = ?,
                    updated_at = ?
                WHERE id = ? AND lovable_status = 'WAITING_FOR_DESIGN'
                """,
                (now, now, job_id),
            )
            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    def claim_next_vercel_job(self) -> Optional[Job]:
        """Atomically claim the next job ready for Vercel deployment.
        Does not block Lovable generation.
        """
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE lovable_status = 'GITHUB_READY'
                  AND vercel_status = 'VERCEL_QUEUED'
                  AND overall_status != 'PAUSED'
                ORDER BY csv_row_index ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            job_id = row["id"]
            cursor.execute(
                """
                UPDATE jobs
                SET vercel_status = 'DEPLOYING',
                    vercel_started_at = ?,
                    updated_at = ?
                WHERE id = ? AND vercel_status = 'VERCEL_QUEUED'
                """,
                (now, now, job_id),
            )
            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    # ---------------- State Transitions & Updates ---------------- #

    def update_design_status(
        self,
        job_id: int,
        status: Union[DesignStatus, str],
        design_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        """Update design status and record completion timestamp/duration if DESIGN_READY."""
        now = now_iso()
        status_val = status.value if hasattr(status, "value") else str(status)
        with transaction(self.db_path) as cursor:
            cursor.execute("SELECT design_started_at FROM jobs WHERE id = ?", (job_id,))
            res = cursor.fetchone()
            started_at = res["design_started_at"] if res else None

            duration = None
            completed_at = None
            if status_val == DesignStatus.DESIGN_READY.value:
                completed_at = now
                duration = calculate_duration_seconds(started_at, completed_at)

            data_str = json.dumps(design_data) if design_data is not None else None

            cursor.execute(
                """
                UPDATE jobs
                SET design_status = ?,
                    design_reference_data = COALESCE(?, design_reference_data),
                    design_completed_at = COALESCE(?, design_completed_at),
                    design_duration_seconds = COALESCE(?, design_duration_seconds),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (status_val, data_str, completed_at, duration, error_message, now, job_id),
            )
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def update_lovable_status(
        self,
        job_id: int,
        status: Union[LovableStatus, str],
        project_id: Optional[str] = None,
        published_url: Optional[str] = None,
        github_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        """Update Lovable status and calculate durations at milestones."""
        now = now_iso()
        status_val = status.value if hasattr(status, "value") else str(status)
        with transaction(self.db_path) as cursor:
            cursor.execute(
                "SELECT lovable_started_at, lovable_published_at FROM jobs WHERE id = ?",
                (job_id,),
            )
            res = cursor.fetchone()
            started_at = res["lovable_started_at"] if res else None
            published_at_prev = res["lovable_published_at"] if res else None

            pub_at = None
            pub_duration = None
            if status_val == LovableStatus.PUBLISHED.value:
                pub_at = now
                pub_duration = calculate_duration_seconds(started_at, pub_at)

            sync_at = None
            sync_duration = None
            lovable_completed_at = None
            lovable_duration = None

            if status_val == LovableStatus.GITHUB_READY.value:
                sync_at = now
                lovable_completed_at = now
                sync_duration = calculate_duration_seconds(
                    published_at_prev or started_at, sync_at
                )
                lovable_duration = calculate_duration_seconds(started_at, lovable_completed_at)

            cursor.execute(
                """
                UPDATE jobs
                SET lovable_status = ?,
                    lovable_project_id = COALESCE(?, lovable_project_id),
                    lovable_published_url = COALESCE(?, lovable_published_url),
                    github_repo_url = COALESCE(?, github_repo_url),
                    lovable_published_at = COALESCE(?, lovable_published_at),
                    lovable_publish_duration_seconds = COALESCE(?, lovable_publish_duration_seconds),
                    github_synced_at = COALESCE(?, github_synced_at),
                    github_sync_duration_seconds = COALESCE(?, github_sync_duration_seconds),
                    lovable_completed_at = COALESCE(?, lovable_completed_at),
                    lovable_duration_seconds = COALESCE(?, lovable_duration_seconds),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status_val,
                    project_id,
                    published_url,
                    github_url,
                    pub_at,
                    pub_duration,
                    sync_at,
                    sync_duration,
                    lovable_completed_at,
                    lovable_duration,
                    error_message,
                    now,
                    job_id,
                ),
            )
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def update_vercel_status(
        self,
        job_id: int,
        status: Union[VercelStatus, str],
        deployment_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        """Update Vercel deployment status and duration."""
        now = now_iso()
        status_val = status.value if hasattr(status, "value") else str(status)
        with transaction(self.db_path) as cursor:
            cursor.execute(
                "SELECT vercel_started_at, created_at FROM jobs WHERE id = ?",
                (job_id,),
            )
            res = cursor.fetchone()
            vercel_started_at = res["vercel_started_at"] if res else None
            created_at = res["created_at"] if res else None

            vercel_completed_at = None
            vercel_duration = None
            job_completed_at = None
            total_duration = None

            if status_val == VercelStatus.DEPLOYED.value:
                vercel_completed_at = now
                vercel_duration = calculate_duration_seconds(vercel_started_at, vercel_completed_at)
                job_completed_at = now
                total_duration = calculate_duration_seconds(created_at, job_completed_at)

            overall = OverallStatus.COMPLETED.value if status_val == VercelStatus.DEPLOYED.value else None

            cursor.execute(
                """
                UPDATE jobs
                SET vercel_status = ?,
                    vercel_deployment_url = COALESCE(?, vercel_deployment_url),
                    vercel_completed_at = COALESCE(?, vercel_completed_at),
                    vercel_duration_seconds = COALESCE(?, vercel_duration_seconds),
                    job_completed_at = COALESCE(?, job_completed_at),
                    total_duration_seconds = COALESCE(?, total_duration_seconds),
                    overall_status = COALESCE(?, overall_status),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status_val,
                    deployment_url,
                    vercel_completed_at,
                    vercel_duration,
                    job_completed_at,
                    total_duration,
                    overall,
                    error_message,
                    now,
                    job_id,
                ),
            )
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def mark_job_failed(self, job_id: int, error_message: str, stage: str) -> Optional[Job]:
        """Mark a job as failed and record error message and stage."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET overall_status = 'FAILED',
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (f"[{stage}] {error_message}", now, job_id),
            )
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def add_log(self, job_id: int, job_uid: str, stage: str, message: str, level: str = "INFO") -> None:
        """Add a structured log entry for a job."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                INSERT INTO job_logs (job_id, job_uid, stage, level, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, job_uid, stage, level, message, now),
            )

    def get_job_logs(self, job_id: int) -> List[JobLog]:
        """Fetch logs for a job."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute(
                "SELECT * FROM job_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            )
            return [JobLog(**dict(r)) for r in cursor.fetchall()]
