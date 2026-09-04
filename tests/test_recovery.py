"""Unit and integration tests for stale job detection and crash recovery."""

from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import JobCreate, DesignStatus, LovableStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.recovery import CrashRecoveryManager


@pytest.fixture
def test_repo(tmp_path: Path):
    db_file = tmp_path / "test_recovery.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    return repo


def test_crash_recovery_determines_ownership_and_preserves_idempotency(test_repo):
    repo = test_repo
    recovery_mgr = CrashRecoveryManager(repository=repo)

    # Job 1: Design worker interrupted while EVALUATING (with reference already populated)
    j1 = repo.create_job(JobCreate(website_url="https://site-1.com", queue_position=1))
    repo.update_design_status(
        j1.id,
        DesignStatus.EVALUATING,
        design_data={
            "design_reference_url": "https://dribbble.com/shots/123",
            "design_score": 0.92,
        },
    )

    # Job 2: Design worker interrupted while SEARCHING (no reference yet)
    j2 = repo.create_job(JobCreate(website_url="https://site-2.com", queue_position=2))
    repo.update_design_status(j2.id, DesignStatus.SEARCHING)

    # Job 3: Lovable worker interrupted while GENERATING (project_id already created)
    j3 = repo.create_job(JobCreate(website_url="https://site-3.com", queue_position=3))
    repo.update_design_status(j3.id, DesignStatus.DESIGN_READY)
    repo.update_lovable_status(
        j3.id,
        LovableStatus.GENERATING,
        project_id="prj_lovable_123",
        editor_url="https://lovable.dev/projects/prj_lovable_123",
    )

    # Job 4: Vercel worker interrupted while DEPLOYING (vercel deployment already created)
    j4 = repo.create_job(JobCreate(website_url="https://site-4.com", queue_position=4))
    repo.update_design_status(j4.id, DesignStatus.DESIGN_READY)
    repo.update_lovable_status(
        j4.id,
        LovableStatus.GITHUB_READY,
        published_url="https://site-4.lovable.app",
        github_url="https://github.com/org/repo_site_4",
    )
    repo.update_vercel_status(
        j4.id,
        VercelStatus.DEPLOYING,
        project_id="prj_vercel_456",
        deployment_id="dpl_vercel_789",
    )

    # Run Crash Recovery
    report = recovery_mgr.recover_interrupted_jobs()

    assert report.recovered_count == 4
    assert report.design_recovered_count == 2
    assert report.lovable_recovered_count == 1
    assert report.vercel_recovered_count == 1

    # Verify Job 1 was advanced to DESIGN_READY because reference was already present
    rec1 = repo.get_job(j1.id)
    assert rec1.design_status == DesignStatus.DESIGN_READY
    assert rec1.design_reference_url == "https://dribbble.com/shots/123"

    # Verify Job 2 was reset to DESIGN_QUEUED for fresh research
    rec2 = repo.get_job(j2.id)
    assert rec2.design_status == DesignStatus.DESIGN_QUEUED

    # Verify Job 3 reset to WAITING_FOR_DESIGN but PRESERVED project_id for credit safety
    rec3 = repo.get_job(j3.id)
    assert rec3.lovable_status == LovableStatus.WAITING_FOR_DESIGN
    assert rec3.lovable_project_id == "prj_lovable_123"
    assert rec3.lovable_editor_url == "https://lovable.dev/projects/prj_lovable_123"

    # Verify Job 4 reset to VERCEL_QUEUED but PRESERVED vercel_project_id and deployment_id
    rec4 = repo.get_job(j4.id)
    assert rec4.vercel_status == VercelStatus.VERCEL_QUEUED
    assert rec4.vercel_project_id == "prj_vercel_456"
    assert rec4.vercel_deployment_id == "dpl_vercel_789"

    # Check audit events
    events = repo.get_job_events(j3.id)
    event_types = [e.event_type for e in events]
    assert "CRASH_RECOVERY" in event_types
