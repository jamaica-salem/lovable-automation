"""Tests for dashboard frontend rendering, static assets, and HTML structure."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_index_html_renders(client):
    """Verify that root endpoint GET / serves the complete dashboard HTML."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    body = res.text

    # Title and branding
    assert "LOVABLE OPS" in body
    assert "Lovable Automation Platform" in body

    # 11 Main Dashboard Metrics
    assert "Total Jobs" in body
    assert "Pending" in body
    assert "Design Research" in body
    assert "Design Ready" in body
    assert "Waiting for Lovable" in body
    assert "Lovable Generating" in body
    assert "Publishing" in body
    assert "GitHub Syncing" in body
    assert "Vercel Deploying" in body
    assert "Completed" in body
    assert "Failed" in body

    # Visual Pipeline Stages
    assert "DESIGN RESEARCH" in body
    assert "LOVABLE WORKER" in body
    assert "GITHUB SYNC" in body
    assert "VERCEL DEPLOY" in body
    assert "PRODUCTION LIVE" in body

    # Operational Focus Cards
    assert "CURRENT LOVABLE JOB" in body
    assert "DESIGN BUFFER" in body
    assert "FLEET &amp; VERCEL OVERVIEW" in body or "FLEET & VERCEL OVERVIEW" in body

    # Table headers
    assert "Website URL &amp; Business" in body or "Website URL & Business" in body
    assert "Overall" in body
    assert "Design" in body
    assert "Lovable" in body
    assert "GitHub" in body
    assert "Vercel" in body
    assert "Lovable App" in body
    assert "Vercel Live" in body
    assert "Duration" in body
    assert "Retries" in body
    assert "Actions" in body

    # Modals
    assert 'id="jobDetailsModal"' in body
    assert 'id="uploadModal"' in body
    assert 'id="confirmModal"' in body
    assert 'id="scheduleModal"' in body
    assert 'id="modal-timeline-list"' in body


def test_static_assets_served(client):
    """Verify CSS and JavaScript static assets load with 200 OK."""
    css_res = client.get("/static/css/style.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")
    assert "--bg-dark" in css_res.text

    js_res = client.get("/static/js/dashboard.js")
    assert js_res.status_code == 200
    assert "fetchStats" in js_res.text
    assert "fetchOrchestratorStatus" in js_res.text
