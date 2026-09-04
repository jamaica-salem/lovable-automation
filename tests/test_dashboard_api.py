"""Tests for dashboard API endpoints including 11-field stats and orchestrator controls."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from database.repository import JobRepository
from database.models import JobCreate, RedesignJob, OverallStatus, DesignStatus, LovableStatus, VercelStatus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def repo():
    return JobRepository()


def test_api_stats_returns_all_eleven_metrics(client, repo):
    """Verify GET /api/stats includes all 11 core production pipeline metrics."""
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()

    required_keys = [
        "total_jobs",
        "pending",
        "design_research",
        "design_ready",
        "waiting_for_lovable",
        "lovable_generating",
        "publishing",
        "github_syncing",
        "vercel_deploying",
        "completed",
        "failed",
    ]

    for key in required_keys:
        assert key in data, f"Missing key: {key}"
        assert isinstance(data[key], int)


def test_orchestrator_status_endpoint(client, repo):
    """Verify GET /api/orchestrator/status returns health, active job, and buffer."""
    # Seed a job with DESIGN_READY to test buffer
    job_in = JobCreate(
        website_url="https://buffer-test.org",
        business_name="Buffer Test Co",
    )
    job = repo.create_job(job_in)
    repo.update_design_status(job.id, DesignStatus.DESIGN_READY)

    res = client.get("/api/orchestrator/status")
    assert res.status_code == 200
    data = res.json()

    assert "health" in data
    assert "active_lovable_job" in data
    assert "ready_buffer_jobs" in data
    assert "workers" in data

    # Verify ready_buffer_jobs is a list
    assert isinstance(data["ready_buffer_jobs"], list)


def test_orchestrator_global_controls(client):
    """Verify start, pause, resume, and stop global controls."""
    res_start = client.post("/api/orchestrator/start")
    assert res_start.status_code == 200
    assert res_start.json()["is_running"] is True

    res_pause = client.post("/api/orchestrator/pause")
    assert res_pause.status_code == 200
    assert res_pause.json()["is_paused"] is True

    res_resume = client.post("/api/orchestrator/resume")
    assert res_resume.status_code == 200
    assert res_resume.json()["is_paused"] is False

    res_stop = client.post("/api/orchestrator/stop")
    assert res_stop.status_code == 200
    assert res_stop.json()["is_running"] is False


def test_orchestrator_individual_worker_controls(client):
    """Verify individual worker pool controls (design, lovable, vercel)."""
    for pool in ["design", "lovable", "vercel"]:
        for action in ["pause", "resume"]:
            res = client.post(f"/api/orchestrator/workers/{pool}/{action}")
            assert res.status_code == 200
            assert "successfully" in res.json()["message"]

    # Invalid pool
    bad_res = client.post("/api/orchestrator/workers/invalid_pool/start")
    assert bad_res.status_code == 400

    # Invalid action
    bad_act = client.post("/api/orchestrator/workers/design/invalid_action")
    assert bad_act.status_code == 400
