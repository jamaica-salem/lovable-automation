"""Base worker class providing async loop management, logging, and graceful shutdown."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from utils.logger import format_log_message, logger


class BaseWorker(ABC):
    """Abstract base worker for background execution pipelines."""

    def __init__(self, name: str, poll_interval: float = 2.0):
        self.name = name
        self.poll_interval = poll_interval
        self._is_running = False
        self._is_paused = False
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        """Check if worker is currently active."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Check if worker is currently paused."""
        return self._is_paused

    def pause(self) -> None:
        """Pause worker processing without terminating background loop."""
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        self._resume_event.clear()
        logger.info(f"Worker {self.name} paused.")

    def resume(self) -> None:
        """Resume worker processing from paused state."""
        if not self._is_running or not self._is_paused:
            return
        self._is_paused = False
        self._resume_event.set()
        logger.info(f"Worker {self.name} resumed.")

    async def start(self) -> None:
        """Start the worker's background async task loop."""
        if self._is_running:
            logger.warning(f"Worker {self.name} is already running.")
            return

        self._is_running = True
        self._is_paused = False
        self._stop_event.clear()
        self._resume_event.set()
        self._task = asyncio.create_task(self._run_loop(), name=f"worker_{self.name}")
        logger.info(f"Worker {self.name} started successfully.")

    async def stop(self) -> None:
        """Signal the worker to stop and await clean termination."""
        if not self._is_running:
            return

        logger.info(f"Worker {self.name} stopping...")
        self._is_running = False
        self._is_paused = False
        self._stop_event.set()
        self._resume_event.set()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"Worker {self.name} stopped.")

    async def _run_loop(self) -> None:
        """Internal execution loop."""
        while self._is_running and not self._stop_event.is_set():
            try:
                if self._is_paused:
                    await self._resume_event.wait()
                    if not self._is_running or self._stop_event.is_set():
                        break

                processed = await self.step()
                if not processed:
                    # No job was claimed, idle wait
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    format_log_message(f"Unhandled error in worker loop: {exc}", stage=self.name),
                    exc_info=True,
                )
                await asyncio.sleep(self.poll_interval)

    @abstractmethod
    async def step(self) -> bool:
        """Perform one unit of work.
        
        Returns:
            bool: True if work was processed (loop continues immediately),
                  False if idle (loop waits poll_interval).
        """
        pass
