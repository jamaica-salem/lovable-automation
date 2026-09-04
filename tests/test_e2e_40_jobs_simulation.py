"""Comprehensive End-to-End 40-job pipeline benchmark simulation.

Target: ~40 websites/day.
Benchmark goal: ~10 minutes/site average throughput target.
Verifies:
  - Concurrent Design research (2 workers) building a buffer (3 ready designs).
  - Strict sequential Lovable execution (1 -> 2 -> ... -> 40, strictly 1 mutex).
  - Concurrent Vercel deployment (2 workers) overlapping Lovable.
  - Calculation of operational throughput metrics (total time, avg/site, sites/hr, utilization).
"""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import JobCreate, OverallStatus, LovableStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.orchestrator import PipelineOrchestrator
from services.dribbble.providers import MockSearchProvider
from services.dribbble.service import DribbbleDesignSearchService
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider
from services.website_analysis.models import WebsiteAnalysis


class FastSimulationAnalyzer:
    """Fast realistic analyzer for 40-job benchmark simulation."""

    async def analyze(self, url: str, business_name: str = None) -> WebsiteAnalysis:
        return WebsiteAnalysis(
            url=url,
            business_name=business_name or "Benchmark Client",
            industry="Healthcare & Wellness",
            category="Medical Clinic",
            summary="Clean modern medical practice with appointment booking",
            detected_colors=["#0F172A", "#0EA5E9"],
            key_sections=["Hero", "Services", "Doctors", "Testimonials", "Contact"],
        )


@pytest.mark.asyncio
async def test_e2e_40_jobs_conveyor_benchmark_simulation(tmp_path: Path):
    """Simulate 40 jobs through concurrent Design, sequential Lovable, and concurrent Vercel."""
    db_file = tmp_path / "test_benchmark_40_jobs.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)

    mock_search = DribbbleDesignSearchService(provider=MockSearchProvider())
    mock_lovable = MockLovableProvider()
    mock_vercel = MockVercelProvider()
    mock_analyzer = FastSimulationAnalyzer()

    # Enqueue 40 jobs in strict CSV order
    num_jobs = 40
    for i in range(1, num_jobs + 1):
        repo.create_job(
            JobCreate(
                website_url=f"https://target-business-{i:02d}.com",
                business_name=f"Business #{i:02d}",
                queue_position=i,
            )
        )

    assert repo.count_jobs() == num_jobs

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

    # Observability tracking
    lovable_claimed_order = []
    active_lovable_history = []
    max_observed_design_buffer = 0

    d_workers = orchestrator.design_workers
    l_worker = orchestrator.lovable_workers[0]
    v_workers = orchestrator.vercel_workers

    # Track claim order via queue.claim_lovable_job
    orig_claim = queue.claim_lovable_job
    def tracked_claim():
        job = orig_claim()
        if job:
            # Verify mutex in action: repository confirms Lovable worker is busy
            assert repo.is_lovable_worker_busy() is True
            # Verify no second job can be claimed concurrently
            assert orig_claim() is None
            lovable_claimed_order.append(job.queue_position)
            active_lovable_history.append(1)
        else:
            active_lovable_history.append(0)
        return job
    queue.claim_lovable_job = tracked_claim

    # Step simulation loop
    max_ticks = 400
    ticks = 0

    while ticks < max_ticks:
        ticks += 1

        # Check ready buffer depth
        current_buffer = repo.get_design_buffer_count()
        if current_buffer > max_observed_design_buffer:
            max_observed_design_buffer = current_buffer

        # Step Design workers concurrently
        for dw in d_workers:
            await dw.step()

        # Step Lovable worker (strictly 1 active mutex)
        await l_worker.step()

        # Step Vercel workers concurrently
        for vw in v_workers:
            await vw.step()

        # Check if all 40 jobs have completed
        stats = repo.get_pipeline_stats()
        if stats.completed == num_jobs:
            break

    # 1. Verification of Completion
    final_stats = repo.get_pipeline_stats()
    assert final_stats.completed == num_jobs, f"Expected 40 completed, got {final_stats.completed}"
    assert final_stats.failed == 0

    # 2. Verification of Strict Queue Ordering (1 -> 2 -> ... -> 40)
    expected_order = list(range(1, num_jobs + 1))
    assert lovable_claimed_order == expected_order, (
        f"Lovable claimed jobs out of order!\nExpected: {expected_order}\nActual: {lovable_claimed_order}"
    )

    # 3. Verification of Design Buffer Management
    assert max_observed_design_buffer >= 2, "Design buffer never accumulated ready designs ahead of Lovable"
    assert max_observed_design_buffer <= 4, "Design workers exceeded allowed buffer limit"

    # 4. Verification of Output Artifacts & URLs
    completed_jobs = repo.list_jobs(limit=50)
    for job in completed_jobs:
        assert job.overall_status == OverallStatus.COMPLETED
        assert job.lovable_published_url is not None
        assert "lovable.app" in job.lovable_published_url
        assert job.vercel_deployment_url is not None
        assert "vercel.app" in job.vercel_deployment_url
        assert job.project_slug is not None
        assert job.retry_count == 0

    # 5. Throughput & KPI Calculations
    metrics = orchestrator.get_metrics()
    assert metrics.completed_jobs == num_jobs
    assert metrics.failure_rate == 0.0
    assert metrics.completed_sites_per_hour > 0.0

    # Average Lovable utilization must be positive
    avg_utilization = sum(active_lovable_history) / max(1, len(active_lovable_history))
    assert avg_utilization > 0.0
