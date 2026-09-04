"""Vercel Worker - non-blocking pipeline for deployment and verification."""

from typing import Optional
from database.models import VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.vercel.interface import StubVercelService, VercelService
from utils.logger import format_log_message, logger
from workers.base import BaseWorker


class VercelWorker(BaseWorker):
    """Worker deploying GitHub repositories to Vercel and verifying live status.
    Operates independently and does NOT block the Lovable worker.
    """

    def __init__(
        self,
        worker_id: str = "vercel-1",
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        vercel_service: Optional[VercelService] = None,
        poll_interval: float = 2.0,
    ):
        super().__init__(name=f"VercelWorker-{worker_id}", poll_interval=poll_interval)
        self.worker_id = worker_id
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)
        self.vercel = vercel_service or StubVercelService()

    async def step(self) -> bool:
        """Attempt to claim and process the next Vercel deployment job."""
        job = self.queue.claim_vercel_job()
        if not job:
            return False

        job_id = job.id
        job_uid = job.job_uid
        repo_url = job.github_repo_url or f"https://github.com/organization/repo_{job_uid}"

        logger.info(
            format_log_message(
                f"Starting Vercel deployment for repository {repo_url}",
                job_id=job_uid,
                stage=self.name,
            )
        )

        try:
            # Stage 1: DEPLOYING -> Deploy project
            self.repo.add_log(job_id, job_uid, "VERCEL_DEPLOYING", f"Triggering deployment for {repo_url}")
            project_name = f"redesign-{job_uid}"
            deployment = await self.vercel.create_deployment(repo_url, project_name)

            # Stage 2: VERIFYING -> Verify live deployment
            self.repo.update_vercel_status(job_id, VercelStatus.VERIFYING)
            self.repo.add_log(
                job_id,
                job_uid,
                "VERCEL_VERIFYING",
                f"Verifying live status at {deployment.deployment_url}",
            )
            is_live = await self.vercel.verify_deployment(deployment.deployment_url)
            if not is_live:
                raise RuntimeError(f"Deployment at {deployment.deployment_url} failed verification")

            # Stage 3: DEPLOYED -> Complete job and calculate total durations
            self.repo.update_vercel_status(
                job_id=job_id,
                status=VercelStatus.DEPLOYED,
                deployment_url=deployment.deployment_url,
                project_id=deployment.deployment_id,
                deployment_id=deployment.deployment_id,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "VERCEL_DEPLOYED",
                f"Deployment verified live at {deployment.deployment_url}. Job completed!",
            )

            logger.info(
                format_log_message(
                    f"Job {job_uid} fully completed! Live at {deployment.deployment_url}",
                    job_id=job_uid,
                    stage=self.name,
                )
            )
            return True

        except Exception as exc:
            err = f"Vercel deployment failed: {str(exc)}"
            logger.error(
                format_log_message(err, job_id=job_uid, stage=self.name),
                exc_info=True,
            )
            self.repo.update_vercel_status(
                job_id=job_id,
                status=VercelStatus.FAILED,
                error_message=err,
            )
            self.repo.add_log(job_id, job_uid, "VERCEL_FAILED", err, level="ERROR")
            return True
