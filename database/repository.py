"""Repository providing atomic SQLite database operations for jobs, events, and metrics."""

import json
import uuid
from typing import Any, Dict, List, Optional, Set, Union
from database.connection import get_db_cursor, transaction
from database.models import (
    DesignStatus,
    GitHubStatus,
    Job,
    JobCreate,
    JobEvent,
    JobLog,
    LovableStatus,
    OverallStatus,
    PipelineStats,
    VercelStatus,
)
from utils.slug import generate_slug
from utils.timestamps import calculate_duration_seconds, now_iso


class JobRepository:
    """Repository handling all database CRUD, atomic state transitions, and audit events."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    def _row_to_job(self, row) -> Job:
        """Convert a sqlite3.Row to a Job Pydantic model."""
        data = dict(row)

        # JSON fields
        for json_field in ("input_metadata", "original_csv_row", "design_reference_data"):
            val = data.get(json_field)
            if isinstance(val, str) and val:
                try:
                    data[json_field] = json.loads(val)
                except Exception:
                    data[json_field] = {} if json_field != "design_reference_data" else None
            elif not val and json_field != "design_reference_data":
                data[json_field] = {}

        # Sync aliases
        if data.get("queue_position") is not None and data.get("csv_row_index") is None:
            data["csv_row_index"] = max(0, data["queue_position"] - 1)
        if data.get("csv_row_index") is not None and data.get("queue_position") is None:
            data["queue_position"] = data["csv_row_index"] + 1

        if data.get("vercel_url") and not data.get("vercel_deployment_url"):
            data["vercel_deployment_url"] = data["vercel_url"]
        if data.get("vercel_deployment_url") and not data.get("vercel_url"):
            data["vercel_url"] = data["vercel_deployment_url"]

        if data.get("github_repository_url") and not data.get("github_repo_url"):
            data["github_repo_url"] = data["github_repository_url"]
        if data.get("github_repo_url") and not data.get("github_repository_url"):
            data["github_repository_url"] = data["github_repo_url"]

        if data.get("published_at") and not data.get("lovable_published_at"):
            data["lovable_published_at"] = data["published_at"]
        if data.get("completed_at") and not data.get("job_completed_at"):
            data["job_completed_at"] = data["completed_at"]

        return Job(**data)

    def list_existing_slugs(self) -> Set[str]:
        """Fetch all non-null project slugs to prevent duplicates."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute("SELECT project_slug FROM jobs WHERE project_slug IS NOT NULL")
            return {r[0] for r in cursor.fetchall() if r[0]}

    def get_job_by_url(self, website_url: str) -> Optional[Job]:
        """Find existing job by URL (normalized comparison)."""
        clean_url = website_url.strip().rstrip("/")
        variants = [clean_url, f"{clean_url}/"]
        if clean_url.startswith("https://"):
            variants.append(clean_url.replace("https://", "http://"))
        elif clean_url.startswith("http://"):
            variants.append(clean_url.replace("http://", "https://"))

        placeholders = ",".join(["?"] * len(variants))
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute(
                f"SELECT * FROM jobs WHERE website_url IN ({placeholders}) LIMIT 1",
                variants,
            )
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def create_job(self, job_in: JobCreate) -> Job:
        """Insert a new job into the persistent database with all Chunk 2 fields."""
        now = now_iso()
        job_uid = f"job_{uuid.uuid4().hex[:12]}"

        # Resolve queue position and row index
        queue_pos = job_in.queue_position
        if queue_pos is None or queue_pos <= 0:
            if job_in.csv_row_index is not None:
                queue_pos = job_in.csv_row_index + 1
            else:
                queue_pos = 1

        csv_row_idx = job_in.csv_row_index if job_in.csv_row_index is not None else (queue_pos - 1)

        # Raw CSV row dictionary
        raw_row = job_in.original_csv_row or job_in.input_metadata or {}
        raw_row_json = json.dumps(raw_row)

        # Business name and deterministic slug
        b_name = job_in.business_name or raw_row.get("business_name") or raw_row.get("company_name") or raw_row.get("name")
        slug = job_in.project_slug
        if not slug:
            existing_slugs = self.list_existing_slugs()
            slug = generate_slug(business_name=b_name, website_url=job_in.website_url, existing_slugs=existing_slugs)

        sql = """
        INSERT INTO jobs (
            job_uid, queue_position, website_url, business_name, project_slug,
            original_csv_row, csv_row_index, input_metadata,
            overall_status, design_status, lovable_status, github_status, vercel_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with transaction(self.db_path) as cursor:
            cursor.execute(
                sql,
                (
                    job_uid,
                    queue_pos,
                    job_in.website_url,
                    b_name,
                    slug,
                    raw_row_json,
                    csv_row_idx,
                    raw_row_json,
                    OverallStatus.PENDING.value,
                    DesignStatus.DESIGN_QUEUED.value,
                    LovableStatus.WAITING_FOR_DESIGN.value,
                    GitHubStatus.GITHUB_PENDING.value,
                    VercelStatus.VERCEL_QUEUED.value,
                    now,
                    now,
                ),
            )
            job_id = cursor.lastrowid

            # Record JOB_CREATED event
            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    "JOB_CREATED",
                    None,
                    OverallStatus.PENDING.value,
                    f"Job enqueued at queue position {queue_pos} for {job_in.website_url}",
                    json.dumps({"slug": slug, "business_name": b_name}),
                    now,
                ),
            )

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
        """List jobs ordered strictly by queue_position."""
        with get_db_cursor(self.db_path) as cursor:
            if status:
                cursor.execute(
                    "SELECT * FROM jobs WHERE overall_status = ? ORDER BY queue_position ASC LIMIT ? OFFSET ?",
                    (status.value, limit, offset),
                )
            else:
                cursor.execute(
                    "SELECT * FROM jobs ORDER BY queue_position ASC LIMIT ? OFFSET ?",
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

    # ---------------- Safe Worker Atomic Claims ---------------- #

    def claim_next_design_job(self) -> Optional[Job]:
        """Atomically claim the next queued design job using safe transactions."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                SELECT * FROM jobs 
                WHERE overall_status IN ('PENDING', 'PROCESSING')
                  AND design_status = 'DESIGN_QUEUED'
                ORDER BY queue_position ASC
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
                return None

            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "DESIGN_STARTED", "DESIGN_QUEUED", "ANALYZING", "Design research worker claimed job", now),
            )

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    def get_design_buffer_count(self) -> int:
        """Count how many jobs are DESIGN_READY and waiting for Lovable processing."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs
                WHERE design_status = 'DESIGN_READY'
                  AND lovable_status = 'WAITING_FOR_DESIGN'
                """
            )
            return cursor.fetchone()[0]

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

    def claim_next_lovable_job(self, skip_blocked_jobs: bool = False) -> Optional[Job]:
        """Atomically claim the next job for Lovable processing.
        
        Strict Queue Ordering (default):
        Lovable processes in STRICT CSV / queue_position order.
        If Job 1 is done and Job 2 is not design-ready:
        Lovable WAITS for Job 2 and does NOT skip to Job 3.
        
        If skip_blocked_jobs is True:
        Lovable may proceed with the next available DESIGN_READY job.
        """
        now = now_iso()
        with transaction(self.db_path) as cursor:
            # 1. Mutex Check: exactly 1 active Lovable job
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
                return None

            if not skip_blocked_jobs:
                # STRICT CSV ORDER:
                # Find the earliest incomplete job in the entire queue that has not finished Lovable
                cursor.execute(
                    """
                    SELECT * FROM jobs
                    WHERE lovable_status NOT IN ('GITHUB_READY')
                      AND overall_status != 'COMPLETED'
                      AND overall_status != 'PAUSED'
                    ORDER BY queue_position ASC
                    LIMIT 1
                    """
                )
                earliest_job = cursor.fetchone()
                if not earliest_job:
                    return None

                # If this earliest job is NOT yet DESIGN_READY, Lovable WAITS!
                if earliest_job["design_status"] != DesignStatus.DESIGN_READY.value:
                    return None

                # If it is DESIGN_READY and WAITING_FOR_DESIGN, claim it
                if earliest_job["lovable_status"] != LovableStatus.WAITING_FOR_DESIGN.value:
                    return None

                candidate_row = earliest_job
            else:
                # Configured to skip blocked jobs: find next DESIGN_READY job
                cursor.execute(
                    """
                    SELECT * FROM jobs
                    WHERE design_status = 'DESIGN_READY'
                      AND lovable_status = 'WAITING_FOR_DESIGN'
                      AND overall_status != 'PAUSED'
                    ORDER BY queue_position ASC
                    LIMIT 1
                    """
                )
                candidate_row = cursor.fetchone()
                if not candidate_row:
                    return None

            job_id = candidate_row["id"]
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

            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "LOVABLE_STARTED", "WAITING_FOR_DESIGN", "PREPARING", "Lovable worker claimed job", now),
            )

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    def claim_next_vercel_job(self) -> Optional[Job]:
        """Atomically claim the next job ready for Vercel deployment."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE lovable_status = 'GITHUB_READY'
                  AND vercel_status = 'VERCEL_QUEUED'
                  AND overall_status != 'PAUSED'
                ORDER BY queue_position ASC
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

            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "VERCEL_STARTED", "VERCEL_QUEUED", "DEPLOYING", "Vercel worker claimed job", now),
            )

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return self._row_to_job(cursor.fetchone())

    # ---------------- State Transitions & Updates with Event Logging ---------------- #

    def record_event(
        self,
        job_id: int,
        event_type: str,
        message: str,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobEvent:
        """Explicitly record a state transition or audit event in job_events."""
        now = now_iso()
        meta_json = json.dumps(metadata or {})
        with transaction(self.db_path) as cursor:
            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, event_type, previous_status, new_status, message, meta_json, now),
            )
            event_id = cursor.lastrowid
            cursor.execute("SELECT * FROM job_events WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            return JobEvent(
                id=row["id"],
                job_id=row["job_id"],
                event_type=row["event_type"],
                previous_status=row["previous_status"],
                new_status=row["new_status"],
                message=row["message"],
                metadata=json.loads(row["metadata"] or "{}"),
                created_at=row["created_at"],
            )

    def get_job_events(self, job_id: int) -> List[JobEvent]:
        """Fetch all recorded events for a job in chronological order."""
        with get_db_cursor(self.db_path) as cursor:
            cursor.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            )
            rows = cursor.fetchall()
            return [
                JobEvent(
                    id=r["id"],
                    job_id=r["job_id"],
                    event_type=r["event_type"],
                    previous_status=r["previous_status"],
                    new_status=r["new_status"],
                    message=r["message"],
                    metadata=json.loads(r["metadata"] or "{}"),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

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
            cursor.execute("SELECT design_status, design_started_at FROM jobs WHERE id = ?", (job_id,))
            res = cursor.fetchone()
            prev_status = res["design_status"] if res else None
            started_at = res["design_started_at"] if res else None

            duration = None
            completed_at = None
            if status_val in (
                DesignStatus.DESIGN_READY.value,
                DesignStatus.DESIGN_NEEDS_REVIEW.value,
                DesignStatus.DESIGN_FAILED.value,
            ):
                completed_at = now
                duration = calculate_duration_seconds(started_at, completed_at)

            # Extract specific reference fields if present
            ref_url = None
            ref_image = None
            ref_title = None
            ref_source = "dribbble"
            ref_score = None
            ref_reason = None
            if design_data and isinstance(design_data, dict):
                sel = design_data.get("selected_reference") or {}
                ref_url = design_data.get("design_reference_url") or sel.get("url")
                ref_image = design_data.get("design_reference_image") or sel.get("image_url")
                ref_title = design_data.get("design_reference_title") or sel.get("title")
                ref_source = design_data.get("design_reference_source") or sel.get("source", "dribbble")
                ref_score = design_data.get("design_score") or sel.get("suitability_score") or sel.get("overall_score")
                ref_reason = (
                    design_data.get("design_reason")
                    or design_data.get("rationale")
                    or sel.get("rationale")
                    or sel.get("evaluation_notes")
                )

            data_str = json.dumps(design_data) if design_data is not None else None

            cursor.execute(
                """
                UPDATE jobs
                SET design_status = ?,
                    design_reference_url = COALESCE(?, design_reference_url),
                    design_reference_image = COALESCE(?, design_reference_image),
                    design_reference_title = COALESCE(?, design_reference_title),
                    design_reference_source = COALESCE(?, design_reference_source),
                    design_score = COALESCE(?, design_score),
                    design_reason = COALESCE(?, design_reason),
                    design_error = COALESCE(?, design_error),
                    design_reference_data = COALESCE(?, design_reference_data),
                    design_completed_at = COALESCE(?, design_completed_at),
                    design_duration_seconds = COALESCE(?, design_duration_seconds),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status_val,
                    ref_url,
                    ref_image,
                    ref_title,
                    ref_source,
                    ref_score,
                    ref_reason,
                    error_message,
                    data_str,
                    completed_at,
                    duration,
                    error_message,
                    now,
                    job_id,
                ),
            )

            # Record event
            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "DESIGN_STATUS_CHANGED", prev_status, status_val, f"Design status set to {status_val}", now),
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
        editor_url: Optional[str] = None,
        preview_url: Optional[str] = None,
        github_url: Optional[str] = None,
        github_repo: Optional[str] = None,
        commit_sha: Optional[str] = None,
        error_message: Optional[str] = None,
        retry_count: Optional[int] = None,
        verification_duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Job]:
        """Update Lovable status and calculate durations at milestones."""
        now = now_iso()
        status_val = status.value if hasattr(status, "value") else str(status)
        with transaction(self.db_path) as cursor:
            cursor.execute(
                "SELECT lovable_status, lovable_started_at, published_at FROM jobs WHERE id = ?",
                (job_id,),
            )
            res = cursor.fetchone()
            prev_status = res["lovable_status"] if res else None
            started_at = res["lovable_started_at"] if res else None
            published_at_prev = res["published_at"] if res else None

            pub_at = None
            pub_duration = None
            lovable_completed_at = None
            lovable_duration = None

            if status_val == LovableStatus.PUBLISHED.value:
                pub_at = now
                pub_duration = calculate_duration_seconds(started_at, pub_at)
                lovable_completed_at = now
                lovable_duration = pub_duration

            sync_at = None
            sync_duration = None
            gh_status = None

            if status_val == LovableStatus.GITHUB_READY.value:
                sync_at = now
                lovable_completed_at = now
                sync_duration = calculate_duration_seconds(published_at_prev or started_at, sync_at)
                lovable_duration = calculate_duration_seconds(started_at, lovable_completed_at)
                gh_status = GitHubStatus.SYNCED.value

            cursor.execute(
                """
                UPDATE jobs
                SET lovable_status = ?,
                    lovable_project_id = COALESCE(?, lovable_project_id),
                    lovable_editor_url = COALESCE(?, lovable_editor_url),
                    lovable_preview_url = COALESCE(?, lovable_preview_url),
                    lovable_published_url = COALESCE(?, lovable_published_url),
                    github_repository = COALESCE(?, github_repository),
                    github_repository_url = COALESCE(?, github_repository_url),
                    github_commit_sha = COALESCE(?, github_commit_sha),
                    github_status = COALESCE(?, github_status),
                    published_at = COALESCE(?, published_at),
                    lovable_published_at = COALESCE(?, lovable_published_at),
                    lovable_publish_duration_seconds = COALESCE(?, lovable_publish_duration_seconds),
                    github_completed_at = COALESCE(?, github_completed_at),
                    github_synced_at = COALESCE(?, github_synced_at),
                    github_sync_duration_seconds = COALESCE(?, github_sync_duration_seconds),
                    lovable_completed_at = COALESCE(?, lovable_completed_at),
                    lovable_duration_seconds = COALESCE(?, lovable_duration_seconds),
                    verification_duration_seconds = COALESCE(?, verification_duration_seconds),
                    retry_count = COALESCE(?, retry_count),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status_val,
                    project_id,
                    editor_url,
                    preview_url,
                    published_url,
                    github_repo,
                    github_url,
                    commit_sha,
                    gh_status,
                    pub_at,
                    pub_at,
                    pub_duration,
                    sync_at,
                    sync_at,
                    sync_duration,
                    lovable_completed_at,
                    lovable_duration,
                    verification_duration_seconds,
                    retry_count,
                    error_message,
                    now,
                    job_id,
                ),
            )

            # Record event
            meta_json = json.dumps(metadata or {})
            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, "LOVABLE_STATUS_CHANGED", prev_status, status_val, f"Lovable status set to {status_val}", meta_json, now),
            )

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def update_vercel_status(
        self,
        job_id: int,
        status: Union[VercelStatus, str],
        deployment_url: Optional[str] = None,
        project_id: Optional[str] = None,
        deployment_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Job]:
        """Update Vercel deployment status and duration."""
        now = now_iso()
        status_val = status.value if hasattr(status, "value") else str(status)
        with transaction(self.db_path) as cursor:
            cursor.execute(
                "SELECT vercel_status, vercel_started_at, created_at FROM jobs WHERE id = ?",
                (job_id,),
            )
            res = cursor.fetchone()
            prev_status = res["vercel_status"] if res else None
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
                    vercel_project_id = COALESCE(?, vercel_project_id),
                    vercel_deployment_id = COALESCE(?, vercel_deployment_id),
                    vercel_url = COALESCE(?, vercel_url),
                    vercel_deployment_url = COALESCE(?, vercel_deployment_url),
                    vercel_completed_at = COALESCE(?, vercel_completed_at),
                    vercel_duration_seconds = COALESCE(?, vercel_duration_seconds),
                    completed_at = COALESCE(?, completed_at),
                    job_completed_at = COALESCE(?, job_completed_at),
                    total_duration_seconds = COALESCE(?, total_duration_seconds),
                    overall_status = COALESCE(?, overall_status),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status_val,
                    project_id,
                    deployment_id,
                    deployment_url,
                    deployment_url,
                    vercel_completed_at,
                    vercel_duration,
                    job_completed_at,
                    job_completed_at,
                    total_duration,
                    overall,
                    error_message,
                    now,
                    job_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "VERCEL_STATUS_CHANGED", prev_status, status_val, f"Vercel status set to {status_val}", now),
            )

            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def mark_job_failed(self, job_id: int, error_message: str, stage: str) -> Optional[Job]:
        """Mark a job as failed and record error message and stage."""
        now = now_iso()
        with transaction(self.db_path) as cursor:
            cursor.execute("SELECT overall_status FROM jobs WHERE id = ?", (job_id,))
            res = cursor.fetchone()
            prev_status = res["overall_status"] if res else None

            msg = f"[{stage}] {error_message}"
            cursor.execute(
                """
                UPDATE jobs
                SET overall_status = 'FAILED',
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (msg, now, job_id),
            )
            cursor.execute(
                """
                INSERT INTO job_events (job_id, event_type, previous_status, new_status, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, "JOB_FAILED", prev_status, "FAILED", msg, now),
            )
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def add_log(self, job_id: int, job_uid: str, stage: str, message: str, level: str = "INFO") -> None:
        """Add a structured log entry for a job (legacy compatibility)."""
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
