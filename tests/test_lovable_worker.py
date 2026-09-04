"""Comprehensive tests for LovableWorker."""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.lovable.provider import MockLovableProvider
from workers.lovable.worker import LovableWorker


@pytest.fixture
def clean_db(tmp_path: Path):
    db_file = tmp_path / "test_lovable_worker.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)
    return repo, queue


@pytest.mark.asyncio
async def test_strict_csv_ordering_and_readiness_wait(clean_db):
    repo, queue = clean_db

    # Create 3 jobs in queue positions 1, 2, 3
    j1 = repo.create_job(JobCreate(website_url="https://site1.com", queue_position=1, business_name="Site 1"))
    j2 = repo.create_job(JobCreate(website_url="https://site2.com", queue_position=2, business_name="Site 2"))
    j3 = repo.create_job(JobCreate(website_url="https://site3.com", queue_position=3, business_name="Site 3"))

    # Design Worker finishes Job 1 and Job 3, but Job 2 is still searching!
    repo.update_design_status(j1.id, DesignStatus.DESIGN_READY, design_data={"industry": "Tech"})
    repo.update_design_status(j2.id, DesignStatus.SEARCHING)
    repo.update_design_status(j3.id, DesignStatus.DESIGN_READY, design_data={"industry": "Tech"})

    provider = MockLovableProvider()
    worker = LovableWorker(worker_id="test-order", repository=repo, queue=queue, provider=provider)

    # 1. Lovable processes Job 1
    processed_1 = await worker.step()
    assert processed_1 is True
    job_1_done = repo.get_job_by_url("https://site1.com")
    assert job_1_done.lovable_published_url is not None

    # 2. READINESS RULE CHECK:
    # Job 2 is STILL in SEARCHING. Job 3 is already DESIGN_READY.
    # Lovable Worker MUST NOT skip Job 2! It must WAIT!
    processed_wait = await worker.step()
    assert processed_wait is False  # Idle wait!

    # Verify Job 3 was NOT claimed
    job_3_check = repo.get_job_by_url("https://site3.com")
    assert job_3_check.lovable_status == LovableStatus.WAITING_FOR_DESIGN

    # 3. Now Job 2 finishes design research -> becomes DESIGN_READY
    repo.update_design_status(j2.id, DesignStatus.DESIGN_READY, design_data={"industry": "Tech"})

    # Lovable Worker NOW claims and processes Job 2 strictly before Job 3!
    processed_2 = await worker.step()
    assert processed_2 is True
    job_2_done = repo.get_job_by_url("https://site2.com")
    assert job_2_done.lovable_published_url is not None

    # 4. Finally Lovable processes Job 3
    processed_3 = await worker.step()
    assert processed_3 is True
    job_3_done = repo.get_job_by_url("https://site3.com")
    assert job_3_done.lovable_published_url is not None


@pytest.mark.asyncio
async def test_credit_safety_prevents_duplicate_project_creation(clean_db):
    repo, queue = clean_db

    j = repo.create_job(
        JobCreate(
            website_url="https://credit-safe.com",
            queue_position=1,
            business_name="Credit Safe Co",
        )
    )
    repo.update_design_status(j.id, DesignStatus.DESIGN_READY, design_data={"industry": "Security"})

    provider = MockLovableProvider()
    worker = LovableWorker(worker_id="test-credit", repository=repo, queue=queue, provider=provider)

    # First run processes successfully
    await worker.step()
    assert provider.created_projects_count == 1
    saved_proj_id = repo.get_job_by_url("https://credit-safe.com").lovable_project_id
    assert saved_proj_id is not None

    # Simulate a retry on the same job (e.g. status reset to WAITING_FOR_DESIGN)
    repo.update_lovable_status(j.id, LovableStatus.WAITING_FOR_DESIGN)

    # Process again -> must REUSE existing project, NOT create a new one!
    await worker.step()
    assert provider.created_projects_count == 1  # Did NOT call create_project again!
    reused_proj_id = repo.get_job_by_url("https://credit-safe.com").lovable_project_id
    assert reused_proj_id == saved_proj_id


@pytest.mark.asyncio
async def test_live_url_verification_and_failure_retry(clean_db):
    repo, queue = clean_db

    j = repo.create_job(
        JobCreate(
            website_url="https://flaky-site.com",
            queue_position=1,
            business_name="Flaky Site",
        )
    )
    repo.update_design_status(j.id, DesignStatus.DESIGN_READY, design_data={"industry": "Testing"})

    provider = MockLovableProvider()
    # Configure provider to simulate URL verification failure
    provider.simulate_failures["fail_verify"] = "502 Bad Gateway from edge proxy"

    worker = LovableWorker(
        worker_id="test-flaky",
        repository=repo,
        queue=queue,
        provider=provider,
        max_retries=1,
    )

    # Attempt 1: fails URL verification -> retry scheduled
    await worker.step()
    job_attempt1 = repo.get_job_by_url("https://flaky-site.com")
    assert job_attempt1.retry_count == 1
    assert "failed: Published URL" in (job_attempt1.error_message or "")
    assert job_attempt1.lovable_status == LovableStatus.WAITING_FOR_DESIGN

    # Attempt 2: still failing -> max retries exceeded -> FAILED
    await worker.step()
    job_failed = repo.get_job_by_url("https://flaky-site.com")
    assert job_failed.lovable_status == LovableStatus.FAILED
    assert job_failed.retry_count == 2
    assert "failed after 1 attempts" in (job_failed.error_message or "")


@pytest.mark.asyncio
async def test_worker_lifecycle_pause_resume_stop(clean_db):
    repo, queue = clean_db
    provider = MockLovableProvider()
    worker = LovableWorker(worker_id="test-life", repository=repo, queue=queue, provider=provider)

    assert not worker.is_running
    assert not worker.is_paused

    await worker.start()
    assert worker.is_running

    worker.pause()
    assert worker.is_paused

    worker.resume()
    assert not worker.is_paused

    await worker.stop()
    assert not worker.is_running
