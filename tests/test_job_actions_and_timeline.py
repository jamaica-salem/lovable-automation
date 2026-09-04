"""Tests for job actions (retry, cancel) and audit event timeline."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from database.repository import JobRepository
from database.models import JobCreate, OverallStatus, DesignStatus, LovableStatus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def repo():
    return JobRepository()


def test_job_events_retrieval(client, repo):
    """Verify GET /api/jobs/{id}/events returns chronological event history."""
    job = repo.create_job(
        JobCreate(
            website_url="https://timeline-test.com",
            business_name="Timeline Test",
        )
    )

    # Log some events
    repo.log_event(job.id, "STATUS_UPDATED", {"status": "PROCESSING"})
    repo.log_event(job.id, "DESIGN_COMPLETED", {"reference": "Dribbble Shot #123"})

    res = client.get(f"/api/jobs/{job.id}/events")
    assert res.status_code == 200
    events = res.json()
    assert len(events) >= 2
    types = [e["event_type"] for e in events]
    assert "STATUS_UPDATED" in types
    assert "DESIGN_COMPLETED" in types


def test_job_retry_action(client, repo):
    """Verify POST /api/jobs/{id}/retry safely resets failed job to queued."""
    job = repo.create_job(
        JobCreate(
            website_url="https://failed-job.com",
            business_name="Failed Job Inc",
        )
    )
    repo.update_job_status(job.id, OverallStatus.FAILED, error_message="Lovable generation timeout")

    res = client.post(f"/api/jobs/{job.id}/retry")
    assert res.status_code == 200
    retried_job = res.json()

    assert retried_job["overall_status"] == OverallStatus.PENDING.value
    assert retried_job["design_status"] == DesignStatus.DESIGN_QUEUED.value
    assert retried_job["lovable_status"] == LovableStatus.WAITING_FOR_DESIGN.value
    assert retried_job["retry_count"] == 1
    assert retried_job.get("error_message") is None

    # Check event was logged
    events = repo.get_job_events(job.id)
    assert any(e.event_type == "JOB_RETRIED" for e in events)


def test_job_cancel_action(client, repo):
    """Verify POST /api/jobs/{id}/cancel cancels pending/processing job."""
    job = repo.create_job(
        JobCreate(
            website_url="https://cancellable-job.com",
            business_name="Cancel Corp",
        )
    )
    repo.update_job_status(job.id, OverallStatus.PROCESSING)

    res = client.post(f"/api/jobs/{job.id}/cancel")
    assert res.status_code == 200
    cancelled_job = res.json()

    assert cancelled_job["overall_status"] == OverallStatus.FAILED.value
    assert "cancelled" in (cancelled_job.get("last_error") or cancelled_job.get("error_message", "")).lower()

    # Check event was logged
    events = repo.get_job_events(job.id)
    assert any(e.event_type == "JOB_CANCELLED" for e in events)
