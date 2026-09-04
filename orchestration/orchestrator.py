"""Pipeline Orchestrator managing concurrent worker pools, lifecycle controls, and health."""

import asyncio
from typing import List, Dict, Any, Optional

from app.config import settings
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.metrics import PipelineMetricsCollector, PipelineMetrics
from orchestration.recovery import CrashRecoveryManager, CrashRecoveryReport
from utils.logger import logger
from workers.base import BaseWorker
from workers.design.worker import DesignResearchWorker
from workers.lovable.worker import LovableWorker
from workers.vercel.worker import VercelWorker


class PipelineOrchestrator:
    """Master orchestrator for the conveyor-belt website redesign pipeline."""

    def __init__(
        self,
        repository: Optional[JobRepository] = None,
        queue: Optional[PersistentJobQueue] = None,
        design_concurrency: Optional[int] = None,
        vercel_concurrency: Optional[int] = None,
        design_buffer_size: Optional[int] = None,
        design_analyzer: Any = None,
        dribbble_client: Any = None,
        lovable_provider: Any = None,
        vercel_provider: Any = None,
    ):
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)

        # Concurrency & buffer configuration
        self.design_concurrency = (
            design_concurrency
            if design_concurrency is not None
            else settings.design_worker_concurrency
        )
        self.vercel_concurrency = (
            vercel_concurrency
            if vercel_concurrency is not None
            else settings.vercel_worker_concurrency
        )
        self.design_buffer_size = (
            design_buffer_size
            if design_buffer_size is not None
            else settings.design_buffer_size
        )

        # Optional injected providers (useful for mocked testing)
        self.design_analyzer = design_analyzer
        self.dribbble_client = dribbble_client
        self.lovable_provider = lovable_provider
        self.vercel_provider = vercel_provider

        # Worker Pools
        self.design_workers: List[DesignResearchWorker] = []
        self.lovable_workers: List[LovableWorker] = []  # Length strictly 1
        self.vercel_workers: List[VercelWorker] = []

        # Subsystems
        self.metrics_collector = PipelineMetricsCollector(self.repo)
        self.recovery_manager = CrashRecoveryManager(self.repo)

        self._is_running = False
        self._is_paused = False

    @property
    def is_running(self) -> bool:
        """Check if pipeline orchestrator is currently active."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Check if pipeline orchestrator is currently paused."""
        return self._is_paused

    @property
    def all_workers(self) -> List[BaseWorker]:
        """Flattened list of all registered workers across pools."""
        return [*self.design_workers, *self.lovable_workers, *self.vercel_workers]

    def _init_workers(self) -> None:
        """Instantiate worker pools based on configured concurrency limits."""
        # 1. Design Worker Pool (Concurrent, buffer-aware)
        if not self.design_workers:
            for i in range(max(1, self.design_concurrency)):
                w = DesignResearchWorker(
                    worker_id=f"design-{i+1}",
                    queue=self.queue,
                    repository=self.repo,
                    buffer_size=self.design_buffer_size,
                    poll_interval=settings.design_poll_interval,
                    analyzer=self.design_analyzer,
                    design_service=self.dribbble_client,
                )
                self.design_workers.append(w)

        # 2. Lovable Worker Pool (STRICTLY concurrency = 1)
        if not self.lovable_workers:
            lovable_w = LovableWorker(
                worker_id="lovable-1",
                queue=self.queue,
                repository=self.repo,
                provider=self.lovable_provider,
                poll_interval=settings.lovable_poll_interval,
            )
            self.lovable_workers.append(lovable_w)

        # 3. Vercel Worker Pool (Concurrent, non-blocking)
        if not self.vercel_workers:
            for i in range(max(1, self.vercel_concurrency)):
                w = VercelWorker(
                    worker_id=f"vercel-{i+1}",
                    queue=self.queue,
                    repository=self.repo,
                    provider=self.vercel_provider,
                    poll_interval=settings.vercel_poll_interval,
                )
                self.vercel_workers.append(w)

    # ---------------- Global Controls ---------------- #

    async def start_all(self) -> None:
        """Perform crash recovery reconciliation, then start all worker pools."""
        if self._is_running:
            logger.warning("PipelineOrchestrator is already running.")
            return

        logger.info("Initializing PipelineOrchestrator and recovering interrupted jobs...")
        self.recovery_manager.recover_interrupted_jobs()

        self._init_workers()
        await asyncio.gather(
            self.start_design(),
            self.start_lovable(),
            self.start_vercel(),
        )

        self._is_running = True
        self._is_paused = False
        logger.info(
            f"PipelineOrchestrator online: {len(self.design_workers)} Design workers (buffer: {self.design_buffer_size}), "
            f"1 Lovable worker (sequential mutex), {len(self.vercel_workers)} Vercel workers."
        )

    async def pause_all(self) -> None:
        """Pause all worker pools (in-flight tasks finish active unit before pausing)."""
        if not self._is_running or self._is_paused:
            return

        self.pause_design()
        self.pause_lovable()
        self.pause_vercel()
        self._is_paused = True
        logger.info("PipelineOrchestrator: All workers paused.")

    async def resume_all(self) -> None:
        """Resume all paused worker pools."""
        if not self._is_running or not self._is_paused:
            return

        self.resume_design()
        self.resume_lovable()
        self.resume_vercel()
        self._is_paused = False
        logger.info("PipelineOrchestrator: All workers resumed.")

    async def stop_all(self) -> None:
        """Gracefully terminate all worker pools."""
        if not self._is_running:
            return

        logger.info("PipelineOrchestrator: Stopping all workers...")
        await asyncio.gather(
            self.stop_design(),
            self.stop_lovable(),
            self.stop_vercel(),
            return_exceptions=True,
        )

        self._is_running = False
        self._is_paused = False
        logger.info("PipelineOrchestrator: All workers stopped.")

    # ---------------- Individual Worker Controls ---------------- #

    # Design Worker Pool Controls
    async def start_design(self) -> None:
        """Start the Design Worker pool."""
        if not self.design_workers:
            self._init_workers()
        tasks = [w.start() for w in self.design_workers if not w.is_running]
        if tasks:
            await asyncio.gather(*tasks)
        logger.info(f"Design Worker pool started ({len(self.design_workers)} workers).")

    def pause_design(self) -> None:
        """Pause the Design Worker pool."""
        for w in self.design_workers:
            w.pause()
        logger.info("Design Worker pool paused.")

    def resume_design(self) -> None:
        """Resume the Design Worker pool."""
        for w in self.design_workers:
            w.resume()
        logger.info("Design Worker pool resumed.")

    async def stop_design(self) -> None:
        """Stop the Design Worker pool."""
        tasks = [w.stop() for w in self.design_workers if w.is_running]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Design Worker pool stopped.")

    # Lovable Worker Controls
    async def start_lovable(self) -> None:
        """Start the Lovable Worker (strictly 1 instance)."""
        if not self.lovable_workers:
            self._init_workers()
        tasks = [w.start() for w in self.lovable_workers if not w.is_running]
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("Lovable Worker started (sequential mutex).")

    def pause_lovable(self) -> None:
        """Pause the Lovable Worker."""
        for w in self.lovable_workers:
            w.pause()
        logger.info("Lovable Worker paused.")

    def resume_lovable(self) -> None:
        """Resume the Lovable Worker."""
        for w in self.lovable_workers:
            w.resume()
        logger.info("Lovable Worker resumed.")

    async def stop_lovable(self) -> None:
        """Stop the Lovable Worker."""
        tasks = [w.stop() for w in self.lovable_workers if w.is_running]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Lovable Worker stopped.")

    # Vercel Worker Pool Controls
    async def start_vercel(self) -> None:
        """Start the Vercel Worker pool."""
        if not self.vercel_workers:
            self._init_workers()
        tasks = [w.start() for w in self.vercel_workers if not w.is_running]
        if tasks:
            await asyncio.gather(*tasks)
        logger.info(f"Vercel Worker pool started ({len(self.vercel_workers)} workers).")

    def pause_vercel(self) -> None:
        """Pause the Vercel Worker pool."""
        for w in self.vercel_workers:
            w.pause()
        logger.info("Vercel Worker pool paused.")

    def resume_vercel(self) -> None:
        """Resume the Vercel Worker pool."""
        for w in self.vercel_workers:
            w.resume()
        logger.info("Vercel Worker pool resumed.")

    async def stop_vercel(self) -> None:
        """Stop the Vercel Worker pool."""
        tasks = [w.stop() for w in self.vercel_workers if w.is_running]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Vercel Worker pool stopped.")

    # ---------------- Health & Observability ---------------- #

    def get_health(self) -> Dict[str, Any]:
        """Check overall orchestrator health, worker pool states, and queue depths."""
        metrics = self.metrics_collector.calculate_metrics()
        ready_buffer = self.repo.get_design_buffer_count()

        return {
            "status": "PAUSED" if self._is_paused else ("RUNNING" if self._is_running else "STOPPED"),
            "is_running": self._is_running,
            "is_paused": self._is_paused,
            "workers": {
                "design": {
                    "total": len(self.design_workers),
                    "running": sum(1 for w in self.design_workers if w.is_running),
                    "paused": sum(1 for w in self.design_workers if w.is_paused),
                    "buffer_count": ready_buffer,
                    "buffer_limit": self.design_buffer_size,
                    "buffer_full": ready_buffer >= self.design_buffer_size,
                },
                "lovable": {
                    "total": len(self.lovable_workers),
                    "running": sum(1 for w in self.lovable_workers if w.is_running),
                    "paused": sum(1 for w in self.lovable_workers if w.is_paused),
                    "busy": self.repo.is_lovable_worker_busy(),
                },
                "vercel": {
                    "total": len(self.vercel_workers),
                    "running": sum(1 for w in self.vercel_workers if w.is_running),
                    "paused": sum(1 for w in self.vercel_workers if w.is_paused),
                },
            },
            "queues": {
                "design_queue_depth": metrics.design_queue_depth,
                "vercel_queue_depth": metrics.vercel_queue_depth,
            },
            "metrics": {
                "uptime_seconds": metrics.uptime_seconds,
                "lovable_utilization": metrics.lovable_utilization,
                "completed_sites_per_hour": metrics.completed_sites_per_hour,
                "failure_rate": metrics.failure_rate,
                "retry_rate": metrics.retry_rate,
            },
        }

    def get_metrics(self) -> PipelineMetrics:
        """Get calculated pipeline KPIs and average stage durations."""
        return self.metrics_collector.calculate_metrics()

    def get_worker_statuses(self) -> List[Dict[str, Any]]:
        """Return status list for all worker instances."""
        return [
            {
                "name": w.name,
                "type": (
                    "design"
                    if isinstance(w, DesignResearchWorker)
                    else ("lovable" if isinstance(w, LovableWorker) else "vercel")
                ),
                "is_running": w.is_running,
                "is_paused": w.is_paused,
                "poll_interval": w.poll_interval,
            }
            for w in self.all_workers
        ]

    def recover_stale_jobs(self) -> CrashRecoveryReport:
        """Manually trigger crash recovery inspection for stale or interrupted jobs."""
        return self.recovery_manager.recover_interrupted_jobs()
