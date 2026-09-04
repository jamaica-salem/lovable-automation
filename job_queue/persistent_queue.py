"""Persistent job queue backed by the SQLite database."""

from typing import Any, Dict, List, Optional
from app.config import settings
from database.connection import transaction
from database.models import (
    Job,
    JobCreate,
    JobEvent,
    OverallStatus,
    PipelineStats,
)
from database.repository import JobRepository
from utils.logger import logger
from utils.timestamps import now_iso


class PersistentJobQueue:
    """Queue service coordinating persistent job progression across decoupled workers."""

    def __init__(self, repository: Optional[JobRepository] = None):
        self.repo = repository or JobRepository()

    def enqueue(
        self,
        website_url: str,
        queue_position: Optional[int] = None,
        business_name: Optional[str] = None,
        original_csv_row: Optional[Dict[str, Any]] = None,
        input_metadata: Optional[Dict[str, Any]] = None,
        csv_row_index: Optional[int] = None,
        allow_duplicates: bool = False,
    ) -> Job:
        """Enqueue a new job from CSV or manual submission with duplicate prevention."""
        raw_row = original_csv_row or input_metadata or {}

        # Duplicate prevention check
        if not allow_duplicates:
            existing = self.repo.get_job_by_url(website_url)
            if existing:
                logger.info(f"Job already exists for {website_url} (ID: {existing.id}, Position: {existing.queue_position}). Skipping duplicate insertion.")
                return existing

        # Assign queue position
        if queue_position is None:
            if csv_row_index is not None:
                queue_position = csv_row_index + 1
            else:
                queue_position = self.repo.count_jobs() + 1

        csv_idx = csv_row_index if csv_row_index is not None else (queue_position - 1)

        job_create = JobCreate(
            website_url=website_url,
            queue_position=queue_position,
            business_name=business_name,
            original_csv_row=raw_row,
            csv_row_index=csv_idx,
            input_metadata=raw_row,
        )
        return self.repo.create_job(job_create)

    def claim_design_job(self) -> Optional[Job]:
        """Claim next job for Design Research (concurrent pipeline)."""
        job = self.repo.claim_next_design_job()
        if job:
            self.repo.add_log(job.id, job.job_uid, "DESIGN", "Claimed by Design Research Worker")
        return job

    def claim_lovable_job(self, skip_blocked_jobs: Optional[bool] = None) -> Optional[Job]:
        """Claim next job for Lovable Worker (sequential, mutex concurrency = 1).
        
        Enforces STRICT CSV queue order by default.
        """
        skip = settings.skip_blocked_jobs if skip_blocked_jobs is None else skip_blocked_jobs
        job = self.repo.claim_next_lovable_job(skip_blocked_jobs=skip)
        if job:
            self.repo.add_log(job.id, job.job_uid, "LOVABLE", "Claimed by Lovable Worker")
        return job

    def claim_vercel_job(self) -> Optional[Job]:
        """Claim next job for Vercel Worker (non-blocking)."""
        job = self.repo.claim_next_vercel_job()
        if job:
            self.repo.add_log(job.id, job.job_uid, "VERCEL", "Claimed by Vercel Worker")
        return job

    def recover_interrupted_jobs(self) -> int:
        """Recover jobs left in transient states after an ungraceful crash or restart."""
        from orchestration.recovery import CrashRecoveryManager
        recovery_mgr = CrashRecoveryManager(self.repo)
        report = recovery_mgr.recover_interrupted_jobs()
        return report.recovered_count

    def record_event(
        self,
        job_id: int,
        event_type: str,
        message: str,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobEvent:
        """Record an audit event."""
        return self.repo.record_event(job_id, event_type, message, previous_status, new_status, metadata)

    def get_job_events(self, job_id: int) -> List[JobEvent]:
        """Get event logs for a job."""
        return self.repo.get_job_events(job_id)

    def get_stats(self) -> PipelineStats:
        """Retrieve dashboard stage summary stats."""
        return self.repo.get_pipeline_stats()

    def get_job(self, job_id: int) -> Optional[Job]:
        """Retrieve job by integer ID."""
        return self.repo.get_job(job_id)

    def get_job_by_uid(self, job_uid: str) -> Optional[Job]:
        """Retrieve job by UID."""
        return self.repo.get_job_by_uid(job_uid)

    def list_jobs(self, limit: int = 100, offset: int = 0, status: Optional[OverallStatus] = None) -> List[Job]:
        """List jobs ordered by queue position."""
        return self.repo.list_jobs(limit=limit, offset=offset, status=status)
