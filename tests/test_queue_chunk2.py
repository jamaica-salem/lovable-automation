"""Tests for Chunk 2 strict queue ordering, configurable skipping, concurrent claiming, and job events."""

import concurrent.futures
from pathlib import Path
import pytest
from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue


@pytest.fixture
def chunk2_queue_env(tmp_path: Path):
    db_file = tmp_path / "chunk2_queue.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repo)
    return queue, repo


def test_strict_queue_ordering_waiting_behavior(chunk2_queue_env):
    """Verify default STRICT CSV queue order:
    Job 1 → Job 2 → Job 3 → Job 4.
    If Job 1 is complete and Job 2 is not design-ready:
    Lovable waits for Job 2 and does NOT skip to Job 3 by default.
    """
    queue, repo = chunk2_queue_env

    # Enqueue 3 jobs
    j1 = queue.enqueue("https://site1.com", queue_position=1, business_name="Site 1")
    j2 = queue.enqueue("https://site2.com", queue_position=2, business_name="Site 2")
    j3 = queue.enqueue("https://site3.com", queue_position=3, business_name="Site 3")

    # Design finishes for Job 1
    repo.update_design_status(j1.id, DesignStatus.DESIGN_READY)
    # Lovable claims Job 1
    claim1 = queue.claim_lovable_job(skip_blocked_jobs=False)
    assert claim1 is not None and claim1.id == j1.id

    # Job 1 finishes Lovable & syncs to GitHub
    repo.update_lovable_status(j1.id, LovableStatus.GITHUB_READY)

    # Now suppose Job 3 finished design research ahead of Job 2:
    # Job 2 is still DESIGN_QUEUED / ANALYZING (not design-ready)
    # Job 3 is DESIGN_READY
    repo.update_design_status(j3.id, DesignStatus.DESIGN_READY)

    # STRICT ORDER TEST:
    # Lovable must WAIT for Job 2! It must NOT skip to Job 3 by default!
    assert queue.claim_lovable_job(skip_blocked_jobs=False) is None

    # CONFIGURABLE SKIP TEST:
    # If skip_blocked_jobs=True, Lovable is allowed to process Job 3
    claim_skip = queue.claim_lovable_job(skip_blocked_jobs=True)
    assert claim_skip is not None
    assert claim_skip.id == j3.id


def test_job_event_creation_and_audit_trail(chunk2_queue_env):
    """Verify that every significant state transition records structured audit events in job_events."""
    queue, repo = chunk2_queue_env

    job = queue.enqueue("https://event-test.com", queue_position=1, business_name="Audit Co")

    # Verify JOB_CREATED event was recorded
    events = repo.get_job_events(job.id)
    assert len(events) >= 1
    assert events[0].event_type == "JOB_CREATED"
    assert events[0].new_status == OverallStatus.PENDING.value

    # Transition design stage
    claimed = queue.claim_design_job()
    assert claimed is not None

    repo.update_design_status(
        job.id,
        DesignStatus.DESIGN_READY,
        design_data={"selected_reference": {"title": "Apex", "url": "https://dribbble.com/1"}},
    )

    events_after_design = repo.get_job_events(job.id)
    event_types = [e.event_type for e in events_after_design]
    assert "DESIGN_STARTED" in event_types
    assert "DESIGN_STATUS_CHANGED" in event_types

    # Verify event structure
    ready_event = next(e for e in events_after_design if e.new_status == DesignStatus.DESIGN_READY.value)
    assert ready_event.previous_status == DesignStatus.ANALYZING.value
    assert ready_event.created_at is not None


def test_concurrent_worker_claiming_safety(chunk2_queue_env):
    """Verify thread-safe atomic claiming: multiple workers attempting to claim simultaneously
    will never claim the same job twice.
    """
    queue, repo = chunk2_queue_env

    # Enqueue 10 design jobs
    jobs = [queue.enqueue(f"https://concurrent-{i}.com", queue_position=i+1) for i in range(10)]

    claimed_jobs = []

    def claim_worker():
        worker_repo = JobRepository(db_path=repo.db_path)
        worker_queue = PersistentJobQueue(worker_repo)
        return worker_queue.claim_design_job()

    # Launch 10 simultaneous threads attempting to claim
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(claim_worker) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                claimed_jobs.append(res.id)

    # Every claimed job must be completely unique (no duplicates)
    assert len(claimed_jobs) == len(set(claimed_jobs))
    assert len(claimed_jobs) == 10
