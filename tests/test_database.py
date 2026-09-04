"""Tests for SQLite database persistence, WAL mode, and repository operations."""

import os
from pathlib import Path
import pytest
from database.migrations import init_db
from database.models import DesignStatus, JobCreate, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_jobs.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    return repo, db_file


def test_job_persistence_across_reconnect(test_db):
    """Verify jobs survive connection closes and restarts (crash persistence)."""
    repo, db_file = test_db

    # Create job
    job_in = JobCreate(
        website_url="https://example.com",
        csv_row_index=0,
        input_metadata={"category": "ecommerce", "tier": "premium"},
    )
    job = repo.create_job(job_in)
    assert job.id is not None
    assert job.overall_status == OverallStatus.PENDING
    assert job.design_status == DesignStatus.DESIGN_QUEUED
    assert job.lovable_status == LovableStatus.WAITING_FOR_DESIGN

    # Simulate fresh repo instance on restart
    new_repo = JobRepository(db_path=db_file)
    reloaded_job = new_repo.get_job(job.id)
    assert reloaded_job is not None
    assert reloaded_job.job_uid == job.job_uid
    assert reloaded_job.input_metadata == {"category": "ecommerce", "tier": "premium"}


def test_atomic_state_transitions_and_durations(test_db):
    """Test updating statuses and verifying duration calculations."""
    repo, _ = test_db

    job = repo.create_job(JobCreate(website_url="https://test.com", csv_row_index=0))

    # Claim for design
    claimed = repo.claim_next_design_job()
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.design_status == DesignStatus.ANALYZING
    assert claimed.overall_status == OverallStatus.PROCESSING
    assert claimed.design_started_at is not None

    # Mark DESIGN_READY
    ready = repo.update_design_status(
        job.id,
        DesignStatus.DESIGN_READY,
        design_data={"industry": "FinTech", "selected_reference": {"id": "ref_1"}},
    )
    assert ready.design_status == DesignStatus.DESIGN_READY
    assert ready.design_completed_at is not None
    assert ready.design_duration_seconds is not None
    assert ready.design_reference_data["industry"] == "FinTech"


def test_pipeline_stats(test_db):
    """Test pipeline stats aggregation."""
    repo, _ = test_db

    repo.create_job(JobCreate(website_url="https://site1.com", csv_row_index=0))
    repo.create_job(JobCreate(website_url="https://site2.com", csv_row_index=1))

    stats = repo.get_pipeline_stats()
    assert stats.total_jobs == 2
    assert stats.pending == 2
    assert stats.design_research == 0
    assert stats.waiting_for_lovable == 0
    assert stats.lovable_processing == 0
    assert stats.completed == 0
    assert stats.failed == 0
