"""Unit and integration tests for PipelineOrchestrator controls and lifecycle."""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.orchestrator import PipelineOrchestrator
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider


@pytest.fixture
def orchestrator_setup(tmp_path: Path):
    db_file = tmp_path / "test_orchestrator.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)

    orchestrator = PipelineOrchestrator(
        repository=repo,
        queue=queue,
        design_concurrency=2,
        vercel_concurrency=2,
        design_buffer_size=3,
        lovable_provider=MockLovableProvider(),
        vercel_provider=MockVercelProvider(),
    )
    return orchestrator, repo, queue


@pytest.mark.asyncio
async def test_orchestrator_global_controls(orchestrator_setup):
    orchestrator, repo, queue = orchestrator_setup

    assert orchestrator.is_running is False
    assert orchestrator.is_paused is False

    # 1. START ALL
    await orchestrator.start_all()
    assert orchestrator.is_running is True
    assert orchestrator.is_paused is False
    assert len(orchestrator.design_workers) == 2
    assert len(orchestrator.lovable_workers) == 1
    assert len(orchestrator.vercel_workers) == 2

    # Check health report
    health = orchestrator.get_health()
    assert health["status"] == "RUNNING"
    assert health["workers"]["design"]["total"] == 2
    assert health["workers"]["lovable"]["total"] == 1
    assert health["workers"]["vercel"]["total"] == 2

    # 2. PAUSE ALL
    await orchestrator.pause_all()
    assert orchestrator.is_paused is True
    assert all(w.is_paused for w in orchestrator.all_workers)
    health = orchestrator.get_health()
    assert health["status"] == "PAUSED"

    # 3. RESUME ALL
    await orchestrator.resume_all()
    assert orchestrator.is_paused is False
    assert all(not w.is_paused for w in orchestrator.all_workers)

    # 4. STOP ALL
    await orchestrator.stop_all()
    assert orchestrator.is_running is False
    assert all(not w.is_running for w in orchestrator.all_workers)


@pytest.mark.asyncio
async def test_orchestrator_individual_controls(orchestrator_setup):
    orchestrator, repo, queue = orchestrator_setup

    orchestrator._init_workers()

    # Design worker controls
    await orchestrator.start_design()
    assert all(w.is_running for w in orchestrator.design_workers)
    orchestrator.pause_design()
    assert all(w.is_paused for w in orchestrator.design_workers)
    orchestrator.resume_design()
    assert all(not w.is_paused for w in orchestrator.design_workers)
    await orchestrator.stop_design()
    assert all(not w.is_running for w in orchestrator.design_workers)

    # Lovable worker controls
    await orchestrator.start_lovable()
    assert all(w.is_running for w in orchestrator.lovable_workers)
    orchestrator.pause_lovable()
    assert all(w.is_paused for w in orchestrator.lovable_workers)
    orchestrator.resume_lovable()
    assert all(not w.is_paused for w in orchestrator.lovable_workers)
    await orchestrator.stop_lovable()
    assert all(not w.is_running for w in orchestrator.lovable_workers)

    # Vercel worker controls
    await orchestrator.start_vercel()
    assert all(w.is_running for w in orchestrator.vercel_workers)
    orchestrator.pause_vercel()
    assert all(w.is_paused for w in orchestrator.vercel_workers)
    orchestrator.resume_vercel()
    assert all(not w.is_paused for w in orchestrator.vercel_workers)
    await orchestrator.stop_vercel()
    assert all(not w.is_running for w in orchestrator.vercel_workers)
