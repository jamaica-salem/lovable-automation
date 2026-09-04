"""Tests for Chunk 3 Design Research Worker."""

import asyncio
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import DesignStatus, JobCreate
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from services.dribbble.candidate import DesignCandidate
from services.dribbble.providers import MockSearchProvider
from services.dribbble.service import DribbbleDesignSearchService
from services.website_analysis.analyzer import HttpWebsiteAnalyzer
from services.website_analysis.models import WebsiteAnalysis
from workers.design.worker import DesignResearchWorker


@pytest.fixture
def clean_db(tmp_path: Path):
    db_file = tmp_path / "test_design_worker.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)
    return repo, queue


@pytest.mark.asyncio
async def test_worker_lifecycle_start_stop_pause_resume(clean_db):
    repo, queue = clean_db
    worker = DesignResearchWorker(worker_id="test-1", repository=repo, queue=queue)

    assert not worker.is_running
    assert not worker.is_paused

    await worker.start()
    assert worker.is_running
    assert not worker.is_paused

    worker.pause()
    assert worker.is_paused

    worker.resume()
    assert not worker.is_paused

    await worker.stop()
    assert not worker.is_running


@pytest.mark.asyncio
async def test_buffer_management_pauses_work_ahead_when_full(clean_db):
    repo, queue = clean_db

    # Insert 4 jobs into queue
    for i in range(1, 5):
        repo.create_job(
            JobCreate(
                website_url=f"https://site-{i}.com",
                business_name=f"Business {i}",
                queue_position=i,
            )
        )

    # Set buffer size to 2
    worker = DesignResearchWorker(
        worker_id="test-buf",
        repository=repo,
        queue=queue,
        buffer_size=2,
    )

    # Step 1: processes job 1 -> DESIGN_READY
    processed_1 = await worker.step()
    assert processed_1 is True
    assert repo.get_design_buffer_count() == 1

    # Step 2: processes job 2 -> DESIGN_READY
    processed_2 = await worker.step()
    assert processed_2 is True
    assert repo.get_design_buffer_count() == 2

    # Step 3: buffer is full (2 >= 2) -> step() should refuse to claim job 3 and return False
    processed_3 = await worker.step()
    assert processed_3 is False
    assert repo.get_design_buffer_count() == 2

    # Check job 3 is still DESIGN_QUEUED
    jobs = repo.list_jobs()
    job_3 = [j for j in jobs if j.queue_position == 3][0]
    assert job_3.design_status == DesignStatus.DESIGN_QUEUED

    # Lovable claims job 1 (moving it from WAITING_FOR_DESIGN to PREPARING)
    repo.claim_next_lovable_job()
    assert repo.get_design_buffer_count() == 1

    # Now buffer has room again (1 < 2) -> worker can claim job 3!
    processed_4 = await worker.step()
    assert processed_4 is True
    assert repo.get_design_buffer_count() == 2


@pytest.mark.asyncio
async def test_per_job_timeout_sets_design_needs_review(clean_db):
    repo, queue = clean_db

    repo.create_job(
        JobCreate(
            website_url="https://slow-site.com",
            business_name="Slow Site",
            queue_position=1,
        )
    )

    # Mock analyzer that sleeps longer than timeout
    class SlowAnalyzer:
        async def analyze(self, url: str, business_name=None):
            await asyncio.sleep(2.0)
            return WebsiteAnalysis(url=url)

    worker = DesignResearchWorker(
        worker_id="test-timeout",
        repository=repo,
        queue=queue,
        analyzer=SlowAnalyzer(),
        timeout_seconds=0.2,  # 200ms timeout
    )

    processed = await worker.step()
    assert processed is True

    jobs = repo.list_jobs()
    job = jobs[0]
    assert job.design_status == DesignStatus.DESIGN_NEEDS_REVIEW
    assert "timed out" in (job.design_reason or "").lower()


@pytest.mark.asyncio
async def test_successful_design_research_populates_reference_and_scores(clean_db):
    repo, queue = clean_db

    repo.create_job(
        JobCreate(
            website_url="https://cloudpulse-tech.io",
            business_name="CloudPulse Tech",
            queue_position=1,
        )
    )

    worker = DesignResearchWorker(
        worker_id="test-success",
        repository=repo,
        queue=queue,
    )

    processed = await worker.step()
    assert processed is True

    jobs = repo.list_jobs()
    job = jobs[0]
    assert job.design_status == DesignStatus.DESIGN_READY
    assert job.design_reference_url is not None
    assert job.design_reference_title is not None
    assert job.design_score is not None
    assert job.design_score >= 0.60
    assert job.design_duration_seconds is not None

    # Check that job_events recorded state transitions
    events = repo.get_job_events(job.id)
    event_types = [e.event_type for e in events]
    assert "DESIGN_STARTED" in event_types
    assert "DESIGN_STATUS_CHANGED" in event_types
