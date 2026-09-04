"""Vercel Worker - independent, non-blocking pipeline for deployment and verification."""

import asyncio
from typing import Any, Dict, Optional
from app.config import settings
from database.models import VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.vercel.interface import VercelService
from services.vercel.models import (
    VercelDeployment,
    VercelProject,
    VercelVerificationResult,
)
from services.vercel.provider import (
    MockVercelProvider,
    OfficialApiVercelProvider,
    VercelProvider,
)
from utils.logger import format_log_message, logger
from utils.slug import generate_slug
from workers.base import BaseWorker


class VercelWorker(BaseWorker):
    """Worker deploying GitHub repositories to Vercel and verifying production URLs.
    
    Operates independently and concurrently with the Lovable Worker:
    Vercel deployment of website #1 does NOT block Lovable from processing website #2.
    """

    def __init__(
        self,
        worker_id: str = "vercel-1",
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        provider: Optional[Any] = None,
        poll_interval: float = 2.0,
        deploy_timeout_seconds: Optional[float] = None,
        verify_timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        # Backward-compatibility alias
        vercel_service: Optional[Any] = None,
    ):
        super().__init__(name=f"VercelWorker-{worker_id}", poll_interval=poll_interval)
        self.worker_id = worker_id
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)

        raw_prov = provider or vercel_service
        if raw_prov is None:
            if settings.vercel_token:
                self.provider: VercelProvider = OfficialApiVercelProvider()
            else:
                self.provider = MockVercelProvider()
        else:
            self.provider = self._adapt_provider(raw_prov)

        self.deploy_timeout_seconds = (
            deploy_timeout_seconds
            if deploy_timeout_seconds is not None
            else settings.vercel_deploy_timeout_seconds
        )
        self.verify_timeout_seconds = (
            verify_timeout_seconds
            if verify_timeout_seconds is not None
            else settings.vercel_verify_timeout_seconds
        )
        self.max_retries = max_retries if max_retries is not None else settings.max_retries

    def _adapt_provider(self, raw: Any) -> VercelProvider:
        """Adapt legacy VercelService to VercelProvider interface if needed."""
        if isinstance(raw, VercelProvider):
            return raw

        class AdapterVercelProvider(VercelProvider):
            def __init__(self, legacy: Any):
                self.legacy = legacy

            async def get_project(self, name_or_id: str):
                return None

            async def create_project(self, name: str, git_repo_url: Optional[str] = None):
                return VercelProject(project_id=f"prj_{name}", name=name, git_repo=git_repo_url)

            async def create_deployment(self, project_id: str, git_repo_url: str):
                res = await self.legacy.create_deployment(git_repo_url, project_id)
                return VercelDeployment(
                    deployment_id=res.deployment_id,
                    project_id=project_id,
                    deployment_url=res.deployment_url,
                    status="READY",
                    is_live=True,
                )

            async def get_deployment_status(self, deployment_id: str):
                return VercelDeployment(
                    deployment_id=deployment_id,
                    project_id="prj_default",
                    deployment_url="https://example.vercel.app",
                    status="READY",
                    is_live=True,
                )

            async def poll_deployment_ready(self, deployment_id: str, timeout_seconds: float = 300.0, poll_interval: float = 0.1):
                return await self.get_deployment_status(deployment_id)

            async def verify_production_url(self, url: str, timeout_seconds: float = 20.0):
                is_live = await self.legacy.verify_deployment(url)
                return VercelVerificationResult(
                    url=url,
                    is_live=is_live,
                    status_code=200 if is_live else 500,
                    response_time_ms=50.0,
                    has_html_content=True,
                )

        return AdapterVercelProvider(raw)

    async def step(self) -> bool:
        """Attempt to claim and process the next Vercel deployment job."""
        job = self.queue.claim_vercel_job()
        if not job:
            return False

        job_id = job.id
        job_uid = job.job_uid
        repo_url = job.github_repository_url or job.github_repo_url or f"https://github.com/{settings.github_org}/repo_{job_uid}"

        logger.info(
            format_log_message(
                f"Claimed job {job_uid} for Vercel deployment ({repo_url})",
                job_id=job_uid,
                stage=self.name,
            )
        )

        try:
            await self._process_job(job, repo_url)
            return True

        except Exception as exc:
            err_msg = str(exc)
            logger.error(
                format_log_message(f"Error during Vercel deployment: {err_msg}", job_id=job_uid, stage=self.name),
                exc_info=True,
            )

            current_retries = job.retry_count or 0
            new_retries = current_retries + 1

            if new_retries <= self.max_retries:
                backoff_seconds = min(60.0, (2 ** current_retries) * 1.0)
                warn_msg = f"Vercel attempt {new_retries}/{self.max_retries} failed: {err_msg}. Backoff {backoff_seconds:.1f}s before retry."
                logger.warning(format_log_message(warn_msg, job_id=job_uid, stage=self.name))

                # Reset to VERCEL_QUEUED to allow safe retry
                self.repo.update_vercel_status(
                    job_id=job_id,
                    status=VercelStatus.VERCEL_QUEUED,
                    error_message=warn_msg,
                    retry_count=new_retries,
                )
                self.repo.add_log(job_id, job_uid, "VERCEL_RETRY", warn_msg, level="WARNING")
                await asyncio.sleep(backoff_seconds)
            else:
                fatal_msg = f"Vercel deployment failed after {self.max_retries} attempts: {err_msg}"
                logger.error(format_log_message(fatal_msg, job_id=job_uid, stage=self.name))
                self.repo.update_vercel_status(
                    job_id=job_id,
                    status=VercelStatus.FAILED,
                    error_message=fatal_msg,
                    retry_count=new_retries,
                )
                self.repo.add_log(job_id, job_uid, "VERCEL_FAILED", fatal_msg, level="ERROR")

            return True

    async def _process_job(self, job: Any, repo_url: str) -> None:
        """Internal multi-stage pipeline: DEPLOYING -> VERIFYING -> DEPLOYED."""
        job_id = job.id
        job_uid = job.job_uid

        # Stage 1: DEPLOYING -> Duplicate check, create project & deployment
        b_name = job.business_name or (job.original_csv_row or {}).get("business_name")
        slug = job.project_slug
        if not slug:
            slug = generate_slug(business_name=b_name, website_url=job.website_url)

        project_name = slug if slug.endswith("-modern") else f"{slug}-modern"

        self.repo.update_vercel_status(job_id, VercelStatus.DEPLOYING)
        self.repo.add_log(
            job_id,
            job_uid,
            "VERCEL_DEPLOYING",
            f"Connecting repository {repo_url} and creating Vercel deployment '{project_name}'",
        )

        project_id = job.vercel_project_id
        if not project_id:
            project = await self.provider.create_project(name=project_name, git_repo_url=repo_url)
            project_id = project.project_id
            self.repo.update_vercel_status(job_id=job_id, status=VercelStatus.DEPLOYING, project_id=project_id)
        else:
            logger.info(f"Reusing existing Vercel project {project_id} (duplicate prevention)")

        deployment_id = job.vercel_deployment_id
        if not deployment_id:
            deployment = await self.provider.create_deployment(project_id=project_id, git_repo_url=repo_url)
            deployment_id = deployment.deployment_id
            self.repo.update_vercel_status(
                job_id=job_id,
                status=VercelStatus.DEPLOYING,
                deployment_id=deployment_id,
                deployment_url=deployment.deployment_url,
            )

        # Stage 2: VERIFYING -> Poll deployment readiness and verify live URL
        self.repo.update_vercel_status(job_id, VercelStatus.VERIFYING)
        self.repo.add_log(
            job_id,
            job_uid,
            "VERCEL_VERIFYING",
            f"Polling build readiness for deployment {deployment_id}",
        )

        ready_deployment = await self.provider.poll_deployment_ready(
            deployment_id=deployment_id,
            timeout_seconds=self.deploy_timeout_seconds,
            poll_interval=1.0,
        )
        confirmed_url = ready_deployment.deployment_url

        # Live URL Verification: DNS/HTTP, status 200, response time, HTML structure
        self.repo.add_log(
            job_id,
            job_uid,
            "VERCEL_VERIFYING_URL",
            f"Performing live production URL verification on {confirmed_url}",
        )
        verification = await self.provider.verify_production_url(
            confirmed_url,
            timeout_seconds=self.verify_timeout_seconds,
        )

        if not verification.is_live:
            raise RuntimeError(
                f"Production URL {confirmed_url} failed live verification: "
                f"{verification.error} (status {verification.status_code}, HTML: {verification.has_html_content})"
            )

        # Stage 3: DEPLOYED -> Complete job and finalize metrics
        self.repo.update_vercel_status(
            job_id=job_id,
            status=VercelStatus.DEPLOYED,
            deployment_url=confirmed_url,
            project_id=project_id,
            deployment_id=deployment_id,
        )
        self.repo.record_event(
            job_id=job_id,
            event_type="VERCEL_DEPLOYED",
            message=f"Production deployment verified live at {confirmed_url}",
            previous_status="VERIFYING",
            new_status=VercelStatus.DEPLOYED.value,
        )
        self.repo.add_log(
            job_id,
            job_uid,
            "VERCEL_DEPLOYED",
            f"Production deployment verified live at {confirmed_url} "
            f"(HTTP {verification.status_code}, {verification.response_time_ms}ms). Job completed!",
        )

        logger.info(
            format_log_message(
                f"Job {job_uid} fully completed! Live at {confirmed_url}",
                job_id=job_uid,
                stage=self.name,
            )
        )
