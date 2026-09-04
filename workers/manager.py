"""Worker manager orchestrating the independent concurrent pipelines."""

from typing import List, Optional, Any
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from workers.base import BaseWorker


class WorkerManager:
    """Backward-compatible WorkerManager delegating to PipelineOrchestrator."""

    def __init__(
        self,
        queue: Optional[PersistentJobQueue] = None,
        repository: Optional[JobRepository] = None,
        design_concurrency: Optional[int] = None,
        vercel_concurrency: Optional[int] = None,
        design_buffer_size: Optional[int] = None,
        design_analyzer: Any = None,
        dribbble_client: Any = None,
        lovable_provider: Any = None,
        vercel_provider: Any = None,
    ):
        from orchestration.orchestrator import PipelineOrchestrator

        self._orchestrator = PipelineOrchestrator(
            repository=repository,
            queue=queue,
            design_concurrency=design_concurrency,
            vercel_concurrency=vercel_concurrency,
            design_buffer_size=design_buffer_size,
            design_analyzer=design_analyzer,
            dribbble_client=dribbble_client,
            lovable_provider=lovable_provider,
            vercel_provider=vercel_provider,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._orchestrator, name)

    @property
    def workers(self) -> List[BaseWorker]:
        return self._orchestrator.all_workers

    @property
    def is_running(self) -> bool:
        return self._orchestrator.is_running

    @property
    def is_paused(self) -> bool:
        return self._orchestrator.is_paused

    async def start_all(self) -> None:
        await self._orchestrator.start_all()

    async def stop_all(self) -> None:
        await self._orchestrator.stop_all()

    async def pause_all(self) -> None:
        await self._orchestrator.pause_all()

    async def resume_all(self) -> None:
        await self._orchestrator.resume_all()

    def get_status(self) -> List[dict]:
        return self._orchestrator.get_worker_statuses()
