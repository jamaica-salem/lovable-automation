"""Design Research Worker - independent, concurrent pipeline that prepares references."""

from typing import Optional
from database.models import DesignStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.dribbble.interface import DesignSearchService, StubDesignSearchService
from services.website_analysis.interface import StubWebsiteAnalyzerService, WebsiteAnalyzerService
from utils.logger import format_log_message, logger
from workers.base import BaseWorker


class DesignResearchWorker(BaseWorker):
    """Independent worker that analyzes websites, finds modern design references,
    and sets DESIGN_READY to allow Lovable processing.
    """

    def __init__(
        self,
        worker_id: str = "design-1",
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        analyzer_service: Optional[WebsiteAnalyzerService] = None,
        design_service: Optional[DesignSearchService] = None,
        poll_interval: float = 2.0,
    ):
        super().__init__(name=f"DesignWorker-{worker_id}", poll_interval=poll_interval)
        self.worker_id = worker_id
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)
        self.analyzer = analyzer_service or StubWebsiteAnalyzerService()
        self.design_search = design_service or StubDesignSearchService()

    async def step(self) -> bool:
        """Attempt to claim and process the next design job."""
        job = self.queue.claim_design_job()
        if not job:
            return False

        job_id = job.id
        job_uid = job.job_uid
        url = job.website_url

        logger.info(
            format_log_message(f"Starting design research for {url}", job_id=job_uid, stage=self.name)
        )

        try:
            # Stage 1: Analyze Website
            self.repo.add_log(job_id, job_uid, "DESIGN_ANALYZING", f"Analyzing site structure: {url}")
            analysis = await self.analyzer.analyze(url)

            # Stage 2: Searching References
            self.repo.update_design_status(job_id, DesignStatus.SEARCHING)
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_SEARCHING",
                f"Searching references for industry: {analysis.industry}",
            )
            candidate_refs = await self.design_search.search_references(
                industry=analysis.industry, category=analysis.category
            )

            # Stage 3: Evaluating References
            self.repo.update_design_status(job_id, DesignStatus.EVALUATING)
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_EVALUATING",
                f"Evaluating {len(candidate_refs)} candidate references",
            )
            selected_ref = await self.design_search.evaluate_and_select_best(
                candidate_refs, analysis.industry
            )

            # Stage 4: Store Reference & Mark DESIGN_READY
            design_payload = {
                "industry": analysis.industry,
                "category": analysis.category,
                "detected_colors": analysis.detected_colors,
                "key_sections": analysis.key_sections,
                "selected_reference": selected_ref.model_dump(),
                "rationale": selected_ref.rationale,
            }

            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_READY,
                design_data=design_payload,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_READY",
                f"Selected reference '{selected_ref.title}' (score: {selected_ref.suitability_score})",
            )

            logger.info(
                format_log_message(
                    f"Design research ready for {url}. Reference: {selected_ref.title}",
                    job_id=job_uid,
                    stage=self.name,
                )
            )
            return True

        except Exception as exc:
            err = f"Design research failed: {str(exc)}"
            logger.error(
                format_log_message(err, job_id=job_uid, stage=self.name),
                exc_info=True,
            )
            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_FAILED,
                error_message=err,
            )
            self.repo.add_log(job_id, job_uid, "DESIGN_FAILED", err, level="ERROR")
            return True
