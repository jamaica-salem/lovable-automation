"""Tests for LovableProvider and MockLovableProvider."""

import pytest
from services.lovable.provider import MockLovableProvider


@pytest.mark.asyncio
async def test_mock_lovable_provider_lifecycle():
    provider = MockLovableProvider()

    # 1. Project creation
    proj = await provider.create_project(
        project_name="apex-fintech-modern",
        initial_message="Redesign fintech dashboard with dark mode and analytics.",
    )
    assert proj.project_id.startswith("lovable_proj_")
    assert "apex-fintech-modern" in proj.editor_url
    assert "lovable.app" in proj.preview_url
    assert provider.created_projects_count == 1

    # 2. Get project
    fetched = await provider.get_project(proj.project_id)
    assert fetched.project_id == proj.project_id

    # 3. Poll completion
    completed = await provider.poll_completion(proj.project_id, timeout_seconds=1.0)
    assert completed is True

    # 4. Deploy project
    deployment = await provider.deploy_project(proj.project_id, name="apex-fintech-modern")
    assert deployment.published_url == "https://apex-fintech-modern.lovable.app"

    # 5. Live URL verification
    verification = await provider.verify_url(deployment.published_url)
    assert verification.is_reachable is True
    assert verification.status_code == 200
    assert verification.response_time_ms > 0
