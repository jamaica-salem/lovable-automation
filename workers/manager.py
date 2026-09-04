"""Worker manager orchestrating the independent concurrent pipelines."""

import asyncio
from typing import List, Optional
from app.config import settings
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from utils.logger import logger
from workers.base import BaseWorker
from workers.design.worker import DesignResearchWorker
from workers.lovable.worker import LovableWorker
from workers.vercel.worker import VercelWorker


class WorkerManager:
    """Orchestrator for managing background worker lifecycles."""

    def __init__(
        self,
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
    ):
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)
        self.workers: List[BaseWorker] = []
        self._is_running = False

    def _init_workers(self) -> None:
        """Initialize worker instances based on concurrency configuration."""
        self.workers = []

        # 1. Concurrent Design Research Workers (working ahead)
        design_concurrency = max(1, settings.design_worker_concurrency)
        for i in range(design_concurrency):
            w = DesignResearchWorker(
                worker_id=f"design-{i+1}",
                queue=self.queue,
                repository=self.repo,
                poll_interval=settings.design_poll_interval,
            )
            self.workers.append(w)

        # 2. Sequential Lovable Worker (STRICTLY concurrency = 1)
        lovable_w = LovableWorker(
            worker_id="lovable-1",
            queue=self.queue,
            repository=self.repo,
            poll_interval=settings.lovable_poll_interval,
        )
        self.workers.append(lovable_w)

        # 3. Vercel Deployment Workers (non-blocking)
        vercel_concurrency = max(1, settings.vercel_worker_concurrency)
        for i in range(vercel_concurrency):
            w = VercelWorker(
                worker_id=f"vercel-{i+1}",
                queue=self.queue,
                repository=self.repo,
                poll_interval=settings.vercel_poll_interval,
            )
            self.workers.append(w)

    async def start_all(self) -> None:
        """Start all workers after recovering any interrupted transient states."""
        if self._is_running:
            return

        logger.info("Initializing WorkerManager and recovering transient job states...")
        self.queue.recover_interrupted_jobs()

        self._init_workers()
        for worker in self.workers:
            await worker.start()

        self._is_running = True
        logger.info(
            f"All workers started successfully: "
            f"{settings.design_worker_concurrency} Design, "
            f"1 Lovable (Sequential Mutex), "
            f"{settings.vercel_worker_concurrency} Vercel."
        )

    async def stop_all(self) -> None:
        """Gracefully terminate all workers."""
        if not self._is_running:
            return

        logger.info("Stopping all workers...")
        stop_tasks = [worker.stop() for worker in self.workers]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        self._is_running = False
        logger.info("All workers stopped.")

    def get_status(self) -> List[dict]:
        """Return status information for all managed workers."""
        return [
            {
                "name": w.name,
                "is_running": w.is_running,
                "poll_interval": w.poll_interval,
            }
            for w in self.workers
        ]
