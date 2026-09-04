"""Comprehensive tests for VercelWorker."""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider
from workers.lovable.worker import LovableWorker
from workers.vercel.worker import VercelWorker


@pytest.fixture
def clean_db(tmp_path: Path):
    db_file = tmp_path / "test_vercel_worker.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)
    return repo, queue


@pytest.mark.asyncio
async def test_vercel_worker_lifecycle_and_state_progression(clean_db):
    repo, queue = clean_db

    # Create job ready for Vercel deployment
    job = repo.create_job(
        JobCreate(
            website_url="https://nyc-petcare.com",
            business_name="NYC Petcare",
            queue_position=1,
        )
    )
    repo.update_design_status(job.id, DesignStatus.DESIGN_READY, design_data={"industry": "Pets"})
    repo.update_lovable_status(
        job.id,
        LovableStatus.GITHUB_READY,
        published_url="https://nyc-petcare-modern.lovable.app",
        github_url="https://github.com/org/nyc-petcare-modern",
    )

    provider = MockVercelProvider()
    worker = VercelWorker(worker_id="test-v", repository=repo, queue=queue, provider=provider)

    # Process Vercel deployment
    processed = await worker.step()
    assert processed is True

    # Verify final database state
    completed_job = repo.get_job_by_url("https://nyc-petcare.com")
    assert completed_job.vercel_status == VercelStatus.DEPLOYED
    assert completed_job.overall_status == OverallStatus.COMPLETED
    assert completed_job.vercel_url == "https://nyc-petcare-modern.vercel.app"
    assert completed_job.vercel_project_id == "prj_nyc-petcare-modern"
    assert completed_job.vercel_deployment_id is not None
    assert completed_job.vercel_duration_seconds is not None
    assert completed_job.total_duration_seconds is not None

    # Check job_events audit trail
    events = repo.get_job_events(job.id)
    event_types = [e.event_type for e in events]
    assert "VERCEL_STARTED" in event_types
    assert "VERCEL_DEPLOYED" in event_types


@pytest.mark.asyncio
async def test_independent_concurrency_vercel_does_not_block_lovable(clean_db):
    repo, queue = clean_db

    # Job 1 is ready for Vercel
    j1 = repo.create_job(JobCreate(website_url="https://site1.com", queue_position=1, business_name="Site 1"))
    repo.update_design_status(j1.id, DesignStatus.DESIGN_READY, design_data={"industry": "Tech"})
    repo.update_lovable_status(j1.id, LovableStatus.GITHUB_READY, github_url="https://github.com/org/site1")

    # Job 2 is ready for Lovable
    j2 = repo.create_job(JobCreate(website_url="https://site2.com", queue_position=2, business_name="Site 2"))
    repo.update_design_status(j2.id, DesignStatus.DESIGN_READY, design_data={"industry": "Retail"})

    lovable_provider = MockLovableProvider()
    vercel_provider = MockVercelProvider()

    lovable_worker = LovableWorker(worker_id="test-l", repository=repo, queue=queue, provider=lovable_provider)
    vercel_worker = VercelWorker(worker_id="test-v", repository=repo, queue=queue, provider=vercel_provider)

    # 1. Vercel worker claims Job 1
    did_v1 = await vercel_worker.step()
    assert did_v1 is True
    assert repo.get_job_by_url("https://site1.com").vercel_status == VercelStatus.DEPLOYED

    # 2. Lovable Worker is NOT blocked: claims and processes Job 2 immediately!
    did_l2 = await lovable_worker.step()
    assert did_l2 is True
    assert repo.get_job_by_url("https://site2.com").lovable_status == LovableStatus.GITHUB_READY


@pytest.mark.asyncio
async def test_vercel_url_verification_failure_and_retry_backoff(clean_db):
    repo, queue = clean_db

    job = repo.create_job(JobCreate(website_url="https://fail-deploy.com", queue_position=1, business_name="Fail Deploy"))
    repo.update_design_status(job.id, DesignStatus.DESIGN_READY, design_data={"industry": "Testing"})
    repo.update_lovable_status(job.id, LovableStatus.GITHUB_READY, github_url="https://github.com/org/fail-deploy")

    provider = MockVercelProvider()
    provider.simulate_failures["fail_verify"] = "500 Internal Server Error"

    worker = VercelWorker(worker_id="test-fail", repository=repo, queue=queue, provider=provider, max_retries=1)

    # Attempt 1: fails verification -> scheduled for retry
    await worker.step()
    j1 = repo.get_job_by_url("https://fail-deploy.com")
    assert j1.retry_count == 1
    assert j1.vercel_status == VercelStatus.VERCEL_QUEUED

    # Attempt 2: still failing -> max retries exceeded -> FAILED
    await worker.step()
    j2 = repo.get_job_by_url("https://fail-deploy.com")
    assert j2.retry_count == 2
    assert j2.vercel_status == VercelStatus.FAILED
    assert "failed after 1 attempts" in (j2.error_message or "")


@pytest.mark.asyncio
async def test_vercel_worker_controls_pause_resume_stop(clean_db):
    repo, queue = clean_db
    provider = MockVercelProvider()
    worker = VercelWorker(worker_id="test-ctrl", repository=repo, queue=queue, provider=provider)

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
