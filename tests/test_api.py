"""Integration tests for FastAPI application, dashboard, and API endpoints."""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app, worker_manager
from database.migrations import init_db


@pytest.mark.asyncio
async def test_dashboard_and_api_endpoints():
    """Verify web server starts with lifespan, serves dashboard HTML and REST APIs."""
    # Ensure workers are initialized and lifespan is triggered
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Health check
            res = await client.get("/healthz")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert len(data["workers"]) > 0

            # 2. HTML Dashboard
            dash_res = await client.get("/")
            assert dash_res.status_code == 200
            assert "Lovable Automation Platform" in dash_res.text
            assert "Total Jobs" in dash_res.text
            assert "Waiting for Lovable" in dash_res.text

            # 3. Stats endpoint
            stats_res = await client.get("/api/stats")
            assert stats_res.status_code == 200
            stats = stats_res.json()
            assert "total_jobs" in stats
            assert "lovable_processing" in stats

            # 4. Jobs listing endpoint
            jobs_res = await client.get("/api/jobs")
            assert jobs_res.status_code == 200
            assert isinstance(jobs_res.json(), list)
