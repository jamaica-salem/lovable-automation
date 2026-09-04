"""End-to-end simulated test for 10 jobs through the concurrent redesign pipeline."""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import JobCreate, DesignStatus, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.orchestrator import PipelineOrchestrator
from services.dribbble.providers import MockSearchProvider
from services.dribbble.service import DribbbleDesignSearchService
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider
from services.website_analysis.models import WebsiteAnalysis


class InstantMockAnalyzer:
    """Instantaneous analyzer for simulation tests."""

    async def analyze(self, url: str, business_name: str = None) -> WebsiteAnalysis:
        return WebsiteAnalysis(
            url=url,
            business_name=business_name or "Test Corp",
            industry="Software & Technology",
            category="SaaS Platform",
            summary="Instant mock analysis",
            detected_colors=["#1E293B", "#3B82F6"],
            key_sections=["Hero", "Features", "Pricing", "Testimonials"],
        )


@pytest.mark.asyncio
async def test_pipeline_10_jobs_conveyor_belt_simulation(tmp_path: Path):
    """Simulate 10 jobs passing through concurrent Design, sequential Lovable, and concurrent Vercel."""
    db_file = tmp_path / "test_simulation_10_jobs.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)

    mock_search = DribbbleDesignSearchService(provider=MockSearchProvider())
    mock_lovable = MockLovableProvider()
    mock_vercel = MockVercelProvider()
    mock_analyzer = InstantMockAnalyzer()

    # Enqueue 10 jobs in strict CSV order
    job_ids = []
    for i in range(1, 11):
        job = repo.create_job(
            JobCreate(
                website_url=f"https://client-site-{i:02d}.com",
                business_name=f"Client Business {i:02d}",
                queue_position=i,
            )
        )
        job_ids.append(job.id)

    assert repo.count_jobs() == 10

    # Initialize PipelineOrchestrator with:
    # - 2 Design workers
    # - 1 Lovable worker (sequential mutex)
    # - 2 Vercel workers
    # - Buffer size = 3 ready designs ahead of Lovable
    orchestrator = PipelineOrchestrator(
        repository=repo,
        queue=queue,
        design_concurrency=2,
        vercel_concurrency=2,
        design_buffer_size=3,
        design_analyzer=mock_analyzer,
        dribbble_client=mock_search,
        lovable_provider=mock_lovable,
        vercel_provider=mock_vercel,
    )
    orchestrator._init_workers()

    # Verify initial health and queue depth
    health = orchestrator.get_health()
    assert health["queues"]["design_queue_depth"] == 10
    assert health["workers"]["design"]["total"] == 2
    assert health["workers"]["lovable"]["total"] == 1
    assert health["workers"]["vercel"]["total"] == 2

    # Track order of Lovable claims to verify strict CSV ordering
    lovable_claimed_order = []
    max_observed_design_buffer = 0

    # Run discrete simulated ticks until all 10 jobs are DEPLOYED/COMPLETED
    # Each tick allows workers to step
    d_workers = orchestrator.design_workers
    l_worker = orchestrator.lovable_workers[0]
    v_workers = orchestrator.vercel_workers

    # Conveyor belt simulation loop
    max_ticks = 150
    ticks = 0
    while ticks < max_ticks:
        ticks += 1

        # Check design buffer size ahead of Lovable
        ready_buffer = repo.get_design_buffer_count()
        if ready_buffer > max_observed_design_buffer:
            max_observed_design_buffer = ready_buffer

        # 1. Step Design Workers (concurrent pool of 2)
        for dw in d_workers:
            await dw.step()

        # 2. Check if Lovable claims a job this tick
        before_busy = repo.is_lovable_worker_busy()
        did_l = await l_worker.step()
        if did_l:
            from database.connection import get_db_cursor
            with get_db_cursor(repo.db_path) as cur:
                cur.execute(
                    "SELECT queue_position FROM jobs WHERE lovable_status IN ('PREPARING', 'SUBMITTING', 'GENERATING', 'VERIFYING', 'PUBLISHING', 'GITHUB_READY') ORDER BY updated_at DESC LIMIT 1"
                )
                r = cur.fetchone()
                if r and (not lovable_claimed_order or lovable_claimed_order[-1] != r[0]):
                    lovable_claimed_order.append(r[0])

        # 3. Step Vercel Workers (concurrent pool of 2)
        for vw in v_workers:
            await vw.step()

        # Check termination condition: all 10 jobs completed
        completed = repo.get_pipeline_stats().completed
        if completed == 10:
            break

    # Verification 1: All 10 jobs successfully completed
    completed_jobs = repo.list_jobs(status=OverallStatus.COMPLETED)
    assert len(completed_jobs) == 10

    # Verification 2: Strict CSV queue ordering for Lovable
    # Lovable must have processed in ascending order: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert lovable_claimed_order == list(range(1, 11))

    # Verification 3: Buffer limit respected
    # The design buffer ahead of Lovable should never exceed buffer_size (3)
    assert max_observed_design_buffer <= 3

    # Verification 4: Idempotency & No duplicate projects/deployments
    lovable_project_ids = set()
    vercel_deployment_ids = set()
    for job in completed_jobs:
        assert job.lovable_status == LovableStatus.GITHUB_READY
        assert job.vercel_status == VercelStatus.DEPLOYED
        assert job.overall_status == OverallStatus.COMPLETED

        # Verify uniqueness of projects and deployments (no duplicates)
        assert job.lovable_project_id is not None
        assert job.lovable_project_id not in lovable_project_ids
        lovable_project_ids.add(job.lovable_project_id)

        assert job.vercel_deployment_id is not None
        assert job.vercel_deployment_id not in vercel_deployment_ids
        vercel_deployment_ids.add(job.vercel_deployment_id)

        # Durations must be recorded
        assert job.design_duration_seconds is not None
        assert job.lovable_duration_seconds is not None
        assert job.vercel_duration_seconds is not None
        assert job.total_duration_seconds is not None

    # Verification 5: Aggregate Pipeline Metrics
    metrics = orchestrator.get_metrics()
    assert metrics.total_jobs == 10
    assert metrics.completed_jobs == 10
    assert metrics.failed_jobs == 0
    assert metrics.failure_rate == 0.0
    assert metrics.retry_rate == 0.0
    assert metrics.design_queue_depth == 0
    assert metrics.vercel_queue_depth == 0
    assert metrics.average_time_per_site is not None
    assert metrics.completed_sites_per_hour > 0.0
