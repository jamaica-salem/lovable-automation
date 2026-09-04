"""Persistent job queue backed by the SQLite database."""

from typing import Any, Dict, List, Optional
from database.connection import transaction
from database.models import (
    Job,
    JobCreate,
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

    def enqueue(self, website_url: str, csv_row_index: int, input_metadata: Optional[Dict[str, Any]] = None) -> Job:
        """Enqueue a new job from CSV or manual submission."""
        job_create = JobCreate(
            website_url=website_url,
            csv_row_index=csv_row_index,
            input_metadata=input_metadata or {},
        )
        job = self.repo.create_job(job_create)
        self.repo.add_log(job.id, job.job_uid, "QUEUE", f"Job enqueued for {website_url} (row {csv_row_index})")
        return job

    def claim_design_job(self) -> Optional[Job]:
        """Claim next job for Design Research (concurrent pipeline)."""
        job = self.repo.claim_next_design_job()
        if job:
            self.repo.add_log(job.id, job.job_uid, "DESIGN", "Claimed by Design Research Worker")
        return job

    def claim_lovable_job(self) -> Optional[Job]:
        """Claim next job for Lovable Worker (sequential, mutex concurrency = 1)."""
        job = self.repo.claim_next_lovable_job()
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
        now = now_iso()
        recovered_count = 0
        with transaction(self.repo.db_path) as cursor:
            # Recover interrupted design jobs
            cursor.execute(
                """
                UPDATE jobs
                SET design_status = 'DESIGN_QUEUED',
                    updated_at = ?
                WHERE design_status IN ('ANALYZING', 'SEARCHING', 'EVALUATING')
                  AND overall_status != 'COMPLETED'
                """,
                (now,),
            )
            recovered_count += cursor.rowcount

            # Recover interrupted lovable jobs in initial phase
            cursor.execute(
                """
                UPDATE jobs
                SET lovable_status = 'WAITING_FOR_DESIGN',
                    updated_at = ?
                WHERE lovable_status IN ('PREPARING', 'SUBMITTING')
                  AND overall_status != 'COMPLETED'
                """,
                (now,),
            )
            recovered_count += cursor.rowcount

        if recovered_count > 0:
            logger.warning(f"Crash recovery: reset {recovered_count} interrupted jobs to clean retry states.")
        return recovered_count

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
        """List jobs."""
        return self.repo.list_jobs(limit=limit, offset=offset, status=status)
