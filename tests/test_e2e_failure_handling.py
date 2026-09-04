import asyncio
from pathlib import Path
from typing import Optional
import pytest

from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus, OverallStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.orchestrator import PipelineOrchestrator
from services.dribbble.providers import MockSearchProvider
from services.dribbble.service import DribbbleDesignSearchService
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider
from services.website_analysis.models import WebsiteAnalysis


class ControllableMockAnalyzer:
    def __init__(self):
        self.fail_job_3 = True

    async def analyze(self, url: str, business_name: Optional[str] = None) -> WebsiteAnalysis:
        if "business-03" in url and self.fail_job_3:
            raise RuntimeError("Simulated transient network timeout analyzing Job #3")
        return WebsiteAnalysis(
            url=url,
            business_name=business_name or "Business Client",
            industry="Healthcare & Wellness",
            category="Medical Clinic",
            summary="Clean modern medical practice with appointment booking",
            detected_colors=["#0F172A", "#0EA5E9"],
            key_sections=["Hero", "Services", "Doctors", "Testimonials", "Contact"],
        )


@pytest.mark.asyncio
async def test_e2e_failure_and_fifo_wait_recovery(tmp_path: Path):
    """Verify FIFO conveyor invariant:
    1. Job #1 & #2 succeed design.
    2. Job #3 fails design.
    3. Job #4 succeeds design.
    4. Lovable processes #1 & #2, then WAITS on #3 (refuses to skip to #4).
    5. Job #3 is retried and succeeds design.
    6. Lovable resumes, processing #3 first, then #4.
    """
    db_file = tmp_path / "test_failure_e2e.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)

    analyzer = ControllableMockAnalyzer()
    search_service = DribbbleDesignSearchService(provider=MockSearchProvider())
    mock_lovable = MockLovableProvider()
    mock_vercel = MockVercelProvider()

    # Enqueue 4 jobs in sequence
    jobs = []
    for i in range(1, 5):
        j = repo.create_job(
            JobCreate(
                website_url=f"https://target-business-{i:02d}.com",
                business_name=f"Business #{i:02d}",
                queue_position=i,
            )
        )
        jobs.append(j)

    orchestrator = PipelineOrchestrator(
        repository=repo,
        queue=queue,
        design_concurrency=2,
        vercel_concurrency=2,
        design_buffer_size=5,
        design_analyzer=analyzer,
        dribbble_client=search_service,
        lovable_provider=mock_lovable,
        vercel_provider=mock_vercel,
    )
    orchestrator._init_workers()

    d_worker = orchestrator.design_workers[0]
    l_worker = orchestrator.lovable_workers[0]
    v_worker = orchestrator.vercel_workers[0]

    lovable_claimed_order = []
    orig_claim = queue.claim_lovable_job

    def tracked_claim():
        job = orig_claim()
        if job:
            lovable_claimed_order.append(job.queue_position)
        return job

    queue.claim_lovable_job = tracked_claim

    # Step 1: Run Design research for all 4 jobs
    # Jobs 1, 2, 4 should succeed. Job 3 will fail.
    for _ in range(8):
        await d_worker.step()

    # Verify status in database
    j1 = repo.get_job_by_id(jobs[0].id)
    j2 = repo.get_job_by_id(jobs[1].id)
    j3 = repo.get_job_by_id(jobs[2].id)
    j4 = repo.get_job_by_id(jobs[3].id)

    assert j1.design_status == DesignStatus.DESIGN_READY
    assert j2.design_status == DesignStatus.DESIGN_READY
    assert j3.design_status == DesignStatus.DESIGN_FAILED
    assert "Simulated transient network timeout" in (j3.error_message or "")
    assert j4.design_status == DesignStatus.DESIGN_READY

    # Step 2: Run Lovable worker
    # Lovable should process Job #1
    claimed_1 = await l_worker.step()
    assert claimed_1 is True
    assert lovable_claimed_order == [1]

    # Lovable should process Job #2
    claimed_2 = await l_worker.step()
    assert claimed_2 is True
    assert lovable_claimed_order == [1, 2]

    # Step 3: Lovable tries to claim next job
    # Job #3 is DESIGN_FAILED. Job #4 is DESIGN_READY.
    # CRITICAL INVARIANT: Lovable must NOT jump to Job #4! It MUST wait!
    for _ in range(3):
        claimed_next = await l_worker.step()
        assert claimed_next is False, "Lovable claimed a job when Job #3 was blocked!"

    # Verify Lovable claimed order is STILL [1, 2]
    assert lovable_claimed_order == [1, 2]

    # Verify Job #4 is untouched by Lovable
    j4_check = repo.get_job_by_id(jobs[3].id)
    assert j4_check.lovable_status == LovableStatus.WAITING_FOR_DESIGN

    # Step 4: Operator / System retries Job #3
    analyzer.fail_job_3 = False  # External issue resolved
    retried_j3 = repo.retry_job(j3.id)
    assert retried_j3 is not None
    assert retried_j3.design_status == DesignStatus.DESIGN_QUEUED
    assert retried_j3.retry_count == 1
    assert retried_j3.error_message is None

    # Step 5: Design worker processes Job #3 retry
    await d_worker.step()
    j3_ready = repo.get_job_by_id(j3.id)
    assert j3_ready.design_status == DesignStatus.DESIGN_READY

    # Step 6: Lovable worker resumes
    # Now Job #3 is DESIGN_READY -> Lovable claims #3!
    claimed_3 = await l_worker.step()
    assert claimed_3 is True
    assert lovable_claimed_order == [1, 2, 3]

    # Next, Lovable claims Job #4!
    claimed_4 = await l_worker.step()
    assert claimed_4 is True
    assert lovable_claimed_order == [1, 2, 3, 4]

    # Step 7: Finish Vercel deployments
    for _ in range(8):
        await v_worker.step()

    # Verify all 4 jobs completed
    stats = repo.get_pipeline_stats()
    assert stats.completed == 4
    assert stats.failed == 0

    final_j3 = repo.get_job_by_id(j3.id)
    assert final_j3.overall_status == OverallStatus.COMPLETED
    assert final_j3.retry_count == 1
    assert final_j3.lovable_published_url is not None
    assert final_j3.vercel_deployment_url is not None
