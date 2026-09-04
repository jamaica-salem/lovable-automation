"""Tests for persistent job queue, worker decoupling, and concurrency mutex."""

from pathlib import Path
import pytest
from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus, OverallStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue


@pytest.fixture
def queue_env(tmp_path: Path):
    db_file = tmp_path / "queue_test.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repo)
    return queue, repo


def test_independent_pipeline_and_lovable_mutex(queue_env):
    """Verify that:
    1. Lovable worker starts website #1 as soon as website #1 is DESIGN_READY.
    2. Design worker can continue working ahead on #2, #3, #4.
    3. Exactly ONE Lovable generation can be active at a time (concurrency = 1).
    """
    queue, repo = queue_env

    # Enqueue 3 websites in CSV order
    j1 = queue.enqueue("https://site1.com", csv_row_index=0)
    j2 = queue.enqueue("https://site2.com", csv_row_index=1)
    j3 = queue.enqueue("https://site3.com", csv_row_index=2)

    # Design worker claims #1
    claim_d1 = queue.claim_design_job()
    assert claim_d1.id == j1.id
    assert claim_d1.design_status == DesignStatus.ANALYZING

    # Lovable cannot claim anything yet because design is not ready
    assert queue.claim_lovable_job() is None

    # Design completes for #1
    repo.update_design_status(j1.id, DesignStatus.DESIGN_READY, design_data={"style": "modern"})

    # Lovable can NOW immediately claim #1 WITHOUT waiting for #2 or #3!
    claim_l1 = queue.claim_lovable_job()
    assert claim_l1 is not None
    assert claim_l1.id == j1.id
    assert claim_l1.lovable_status == LovableStatus.PREPARING

    # Meanwhile, Design worker continues working ahead and claims #2!
    claim_d2 = queue.claim_design_job()
    assert claim_d2 is not None
    assert claim_d2.id == j2.id

    # Design worker finishes #2
    repo.update_design_status(j2.id, DesignStatus.DESIGN_READY, design_data={"style": "clean"})

    # STRICT CONCURRENCY MUTEX CHECK:
    # Even though website #2 is DESIGN_READY, Lovable CANNOT claim #2 because #1 is still active in Lovable!
    assert queue.claim_lovable_job() is None
    assert repo.is_lovable_worker_busy() is True

    # Advance #1 through Lovable stages up to GITHUB_READY
    repo.update_lovable_status(j1.id, LovableStatus.GENERATING)
    assert queue.claim_lovable_job() is None  # Still locked

    repo.update_lovable_status(j1.id, LovableStatus.PUBLISHED, published_url="https://site1.lovable.app")
    assert queue.claim_lovable_job() is None  # Still locked

    # Hand off to GitHub: Lovable finishes #1 by marking GITHUB_READY
    repo.update_lovable_status(j1.id, LovableStatus.GITHUB_READY, github_url="https://github.com/org/site1")
    assert repo.is_lovable_worker_busy() is False

    # Now Lovable worker is released and immediately claims #2!
    claim_l2 = queue.claim_lovable_job()
    assert claim_l2 is not None
    assert claim_l2.id == j2.id
    assert claim_l2.lovable_status == LovableStatus.PREPARING


def test_crash_recovery(queue_env):
    """Verify interrupted transient jobs are recovered on startup."""
    queue, repo = queue_env

    j1 = queue.enqueue("https://site1.com", csv_row_index=0)
    repo.update_design_status(j1.id, DesignStatus.ANALYZING)
    repo.claim_next_design_job()  # Overall status -> PROCESSING

    # Simulate app crash and recovery
    recovered = queue.recover_interrupted_jobs()
    assert recovered >= 1

    reloaded = repo.get_job(j1.id)
    assert reloaded.design_status == DesignStatus.DESIGN_QUEUED
