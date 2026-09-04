"""Design Research Worker - independent, concurrent pipeline that prepares references."""

import asyncio
from typing import Any, Dict, Optional
from app.config import settings
from database.models import DesignStatus, Job
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from prompts.reference_rules import format_reference_directive
from services.dribbble.candidate import DesignCandidate
from services.dribbble.interface import DesignReference, DesignSearchService
from services.dribbble.service import DribbbleDesignSearchService
from services.website_analysis.analyzer import HttpWebsiteAnalyzer
from services.website_analysis.interface import WebsiteAnalyzerService
from services.website_analysis.models import WebsiteAnalysis
from utils.logger import format_log_message, logger
from workers.base import BaseWorker


class DesignResearchWorker(BaseWorker):
    """Independent worker that analyzes websites, finds modern design references,
    and sets DESIGN_READY to allow Lovable processing.
    
    Operates concurrently and maintains a configurable buffer ahead of the Lovable Worker.
    """

    def __init__(
        self,
        worker_id: str = "design-1",
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        analyzer: Optional[Any] = None,
        design_service: Optional[Any] = None,
        # Legacy parameter alias
        analyzer_service: Optional[Any] = None,
        buffer_size: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval: float = 2.0,
    ):
        super().__init__(name=f"DesignWorker-{worker_id}", poll_interval=poll_interval)
        self.worker_id = worker_id
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)

        # Services with fallback defaults
        self.analyzer = analyzer or analyzer_service or HttpWebsiteAnalyzer()
        self.design_service = design_service or DribbbleDesignSearchService()

        # Operational buffer & timeout configuration
        self.buffer_size = buffer_size if buffer_size is not None else settings.design_buffer_size
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.design_timeout_seconds
        )

    async def step(self) -> bool:
        """Attempt to claim and process the next design job.
        
        Enforces buffer management, state progression, timeouts, and ranking thresholds.
        """
        # 1. Buffer Management: do not over-fill the ready design queue ahead of Lovable
        current_buffer = self.repo.get_design_buffer_count()
        if current_buffer >= self.buffer_size:
            logger.debug(
                f"[{self.name}] Design buffer full ({current_buffer}/{self.buffer_size} ready). Waiting for Lovable."
            )
            return False

        # 2. Claim next queued job atomically
        job = self.queue.claim_design_job()
        if not job:
            return False

        job_id = job.id
        job_uid = job.job_uid
        url = job.website_url

        logger.info(
            format_log_message(f"Claimed job {job_uid} for design research ({url})", job_id=job_uid, stage=self.name)
        )

        try:
            # Enforce strict per-job timeout
            await asyncio.wait_for(
                self._execute_research_pipeline(job),
                timeout=self.timeout_seconds,
            )
            return True

        except asyncio.TimeoutError:
            timeout_msg = f"Design research timed out after {self.timeout_seconds:.1f}s"
            logger.warning(
                format_log_message(timeout_msg, job_id=job_uid, stage=self.name)
            )
            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_NEEDS_REVIEW,
                design_data={
                    "design_reason": timeout_msg,
                    "timeout": True,
                    "offline_fallback": True,
                },
                error_message=timeout_msg,
            )
            self.repo.add_log(job_id, job_uid, "DESIGN_TIMEOUT", timeout_msg, level="WARNING")
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

    async def _execute_research_pipeline(self, job: Job) -> None:
        """Internal multi-stage pipeline: ANALYZING -> SEARCHING -> EVALUATING -> READY/REVIEW."""
        job_id = job.id
        job_uid = job.job_uid
        url = job.website_url

        # Stage 1: Analyze Website
        self.repo.add_log(job_id, job_uid, "DESIGN_ANALYZING", f"Inspecting website architecture: {url}")
        
        # Support both HttpWebsiteAnalyzer and legacy WebsiteAnalyzerService
        if hasattr(self.analyzer, "analyze"):
            import inspect
            sig = inspect.signature(self.analyzer.analyze)
            if "business_name" in sig.parameters:
                analysis = await self.analyzer.analyze(url, business_name=job.business_name)
            else:
                analysis = await self.analyzer.analyze(url)
        else:
            raise RuntimeError(f"Analyzer {type(self.analyzer)} does not implement analyze()")

        # If analysis is not WebsiteAnalysis (e.g. legacy WebsiteAnalysisResult), upgrade it
        if not isinstance(analysis, WebsiteAnalysis):
            analysis = WebsiteAnalysis(
                url=getattr(analysis, "url", url),
                industry=getattr(analysis, "industry", "Technology & Business Services"),
                category=getattr(analysis, "category", "Corporate Website"),
                summary=getattr(analysis, "summary", ""),
                detected_colors=getattr(analysis, "detected_colors", []),
                key_sections=getattr(analysis, "key_sections", []),
                suggested_improvements=getattr(analysis, "suggested_improvements", []),
            )

        # Stage 2: Searching References
        self.repo.update_design_status(job_id, DesignStatus.SEARCHING)
        self.repo.add_log(
            job_id,
            job_uid,
            "DESIGN_SEARCHING",
            f"Searching references for {analysis.industry} ({analysis.category})",
        )

        best_ref: Optional[DesignCandidate] = None
        needs_review = False

        if hasattr(self.design_service, "search_and_evaluate"):
            best_ref, needs_review, _ = await self.design_service.search_and_evaluate(analysis)
        elif hasattr(self.design_service, "search_references"):
            # Compatibility path for legacy interface
            candidate_refs = await self.design_service.search_references(
                industry=analysis.industry, category=analysis.category
            )
            self.repo.update_design_status(job_id, DesignStatus.EVALUATING)
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_EVALUATING",
                f"Evaluating {len(candidate_refs)} candidate references",
            )
            legacy_best = await self.design_service.evaluate_and_select_best(
                candidate_refs, analysis.industry
            )
            best_ref = DesignCandidate(
                id=legacy_best.reference_id,
                title=legacy_best.title,
                url=legacy_best.url,
                image_url=legacy_best.image_url,
                author=legacy_best.author,
                source=legacy_best.source,
                tags=legacy_best.tags,
                color_palette=legacy_best.color_palette,
                overall_score=legacy_best.suitability_score,
                evaluation_notes=legacy_best.rationale,
            )
            needs_review = best_ref.overall_score < 0.60
        else:
            raise RuntimeError(f"Design service {type(self.design_service)} has unrecognized interface")

        # Stage 3: Evaluating References (ensure state was reflected)
        self.repo.update_design_status(job_id, DesignStatus.EVALUATING)

        # Stage 4: Check evaluation results
        if not best_ref:
            reason = "No candidate design references could be found matching website criteria."
            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_NEEDS_REVIEW,
                design_data={
                    "industry": analysis.industry,
                    "category": analysis.category,
                    "design_reason": reason,
                    "analysis": analysis.model_dump(),
                },
            )
            self.repo.add_log(job_id, job_uid, "DESIGN_NEEDS_REVIEW", reason, level="WARNING")
            logger.warning(format_log_message(reason, job_id=job_uid, stage=self.name))
            return

        # Prepare payload
        directive = format_reference_directive(best_ref.title, best_ref.source)
        design_payload: Dict[str, Any] = {
            "industry": analysis.industry,
            "category": analysis.category,
            "detected_colors": analysis.detected_colors,
            "key_sections": analysis.key_sections,
            "selected_reference": best_ref.model_dump(),
            "design_reference_url": best_ref.url,
            "design_reference_image": best_ref.image_url,
            "design_reference_title": best_ref.title,
            "design_reference_source": best_ref.source,
            "design_score": best_ref.overall_score,
            "design_reason": best_ref.evaluation_notes,
            "analysis": analysis.model_dump(),
            "reference_directive": directive,
        }

        if needs_review:
            review_reason = (
                f"Candidate score {best_ref.overall_score:.2f} is below minimum threshold (0.60). "
                f"{best_ref.evaluation_notes}"
            )
            design_payload["design_reason"] = review_reason
            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_NEEDS_REVIEW,
                design_data=design_payload,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_NEEDS_REVIEW",
                review_reason,
                level="WARNING",
            )
            logger.info(
                format_log_message(
                    f"Design for {url} flagged for review (score: {best_ref.overall_score:.2f})",
                    job_id=job_uid,
                    stage=self.name,
                )
            )
        else:
            self.repo.update_design_status(
                job_id=job_id,
                status=DesignStatus.DESIGN_READY,
                design_data=design_payload,
            )
            self.repo.add_log(
                job_id,
                job_uid,
                "DESIGN_READY",
                f"Selected reference '{best_ref.title}' (score: {best_ref.overall_score:.2f})",
            )
            logger.info(
                format_log_message(
                    f"Design research ready for {url}. Reference: '{best_ref.title}' (score: {best_ref.overall_score:.2f})",
                    job_id=job_uid,
                    stage=self.name,
                )
            )
