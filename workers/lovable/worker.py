"""Lovable Worker - sequential pipeline that executes exactly ONE redesign at a time."""

from typing import Optional
from database.models import LovableStatus
from database.repository import JobRepository
from prompts.templates import generate_redesign_prompt
from job_queue.persistent_queue import PersistentJobQueue
from services.github.interface import GitHubService, StubGitHubService
from services.lovable.interface import LovableService, StubLovableService
from utils.logger import format_log_message, logger
from workers.base import BaseWorker


class LovableWorker(BaseWorker):
    """Sequential worker executing redesign in Lovable.
    
    Invariants enforced:
    1. Exactly ONE active generation at any time (concurrency = 1).
    2. Websites are processed in strict CSV order.
    3. Starts immediately as soon as a single job has DESIGN_READY,
       without waiting for the full queue.
    """

    def __init__(
        self,
        worker_id: str = "lovable-1",
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        lovable_service: Optional[LovableService] = None,
        github_service: Optional[GitHubService] = None,
        poll_interval: float = 2.0,
    ):
        super().__init__(name=f"LovableWorker-{worker_id}", poll_interval=poll_interval)
        self.worker_id = worker_id
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)
        self.lovable = lovable_service or StubLovableService()
        self.github = github_service or StubGitHubService()

    async def step(self) -> bool:
        """Attempt to claim and process the next Lovable job."""
        # Atomic claim checks that concurrency mutex is respected and design is ready
        job = self.queue.claim_lovable_job()
        if not job:
            return False

        job_id = job.id
        job_uid = job.job_uid
        url = job.website_url

        logger.info(
            format_log_message(
                f"Starting Lovable redesign generation for {url} (row {job.csv_row_index})",
                job_id=job_uid,
                stage=self.name,
            )
        )

        try:
            # Stage 1: PREPARING -> Assemble prompt from design research
            design_data = job.design_reference_data or {}
            industry = design_data.get("industry", "Technology")
            category = design_data.get("category", "SaaS")
            ref_dict = design_data.get("selected_reference", {})
            detected_colors = design_data.get("detected_colors", [])

            prompt = generate_redesign_prompt(
                website_url=url,
                industry=industry,
                category=category,
                design_reference=ref_dict,
                detected_colors=detected_colors,
            )

            # Stage 2: SUBMITTING -> Create project and submit prompt
            self.repo.update_lovable_status(job_id, LovableStatus.SUBMITTING)
            self.repo.add_log(job_id, job_uid, "LOVABLE_SUBMITTING", f"Creating project for {url}")
            project_name = f"redesign_{job_uid}"
            project = await self.lovable.create_project(name=project_name, prompt=prompt)

            # Stage 3: GENERATING -> Await generation completion
            self.repo.update_lovable_status(
                job_id,
                LovableStatus.GENERATING,
                project_id=project.project_id,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "LOVABLE_GENERATING",
                f"Generation underway for project {project.project_id}",
            )
            gen_ok = await self.lovable.submit_prompt_and_generate(project.project_id, prompt)
            if not gen_ok:
                raise RuntimeError("Lovable generation did not complete successfully")

            # Stage 4: VERIFYING -> Verify build integrity
            self.repo.update_lovable_status(job_id, LovableStatus.VERIFYING)
            self.repo.add_log(job_id, job_uid, "LOVABLE_VERIFYING", "Verifying generation integrity")
            verified = await self.lovable.verify_generation_completed(project.project_id)
            if not verified:
                raise RuntimeError("Lovable generation verification failed")

            # Stage 5: PUBLISHING -> Publish project
            self.repo.update_lovable_status(job_id, LovableStatus.PUBLISHING)
            self.repo.add_log(job_id, job_uid, "LOVABLE_PUBLISHING", "Publishing to lovable.app")
            publish_res = await self.lovable.publish_project(project.project_id)

            self.repo.update_lovable_status(
                job_id,
                LovableStatus.PUBLISHED,
                published_url=publish_res.published_url,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "LOVABLE_PUBLISHED",
                f"Published live at {publish_res.published_url}",
            )

            # Stage 6: GITHUB_SYNCING -> Export code to GitHub
            self.repo.update_lovable_status(job_id, LovableStatus.GITHUB_SYNCING)
            self.repo.add_log(job_id, job_uid, "LOVABLE_GITHUB_SYNCING", "Synchronizing to GitHub")
            gh_res = await self.lovable.export_to_github(project.project_id, project_name)

            # Stage 7: GITHUB_READY -> Hand off to Vercel worker
            gh_status = await self.github.verify_sync(gh_res.github_repo_url)
            if not gh_status.is_ready:
                raise RuntimeError(f"GitHub synchronization check failed: {gh_status.error_message}")

            self.repo.update_lovable_status(
                job_id,
                LovableStatus.GITHUB_READY,
                github_url=gh_res.github_repo_url,
                github_repo=project_name,
                commit_sha=gh_status.latest_commit,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "GITHUB_READY",
                f"GitHub sync verified at {gh_res.github_repo_url}. Lovable worker released.",
            )

            logger.info(
                format_log_message(
                    f"Lovable generation and GitHub sync completed for {url}. Ready for Vercel deployment.",
                    job_id=job_uid,
                    stage=self.name,
                )
            )
            # True indicates work done; next loop iteration will evaluate mutex for next job
            return True

        except Exception as exc:
            err = f"Lovable processing failed: {str(exc)}"
            logger.error(
                format_log_message(err, job_id=job_uid, stage=self.name),
                exc_info=True,
            )
            self.repo.update_lovable_status(
                job_id=job_id,
                status=LovableStatus.FAILED,
                error_message=err,
            )
            self.repo.add_log(job_id, job_uid, "LOVABLE_FAILED", err, level="ERROR")
            return True
