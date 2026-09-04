"""Tests for VercelProvider and MockVercelProvider."""

import pytest
from services.vercel.provider import MockVercelProvider


@pytest.mark.asyncio
async def test_vercel_provider_project_and_deployment_lifecycle():
    provider = MockVercelProvider()

    # 1. Project creation
    project = await provider.create_project(
        name="nyc-petcare-modern",
        git_repo_url="https://github.com/org/nyc-petcare-modern",
    )
    assert project.project_id == "prj_nyc-petcare-modern"
    assert provider.created_projects_count == 1

    # Duplicate project check: creating with same name returns existing project
    dup_project = await provider.create_project(name="nyc-petcare-modern")
    assert dup_project.project_id == project.project_id
    assert provider.created_projects_count == 1

    # 2. Deployment creation
    deployment = await provider.create_deployment(
        project_id=project.project_id,
        git_repo_url="https://github.com/org/nyc-petcare-modern",
    )
    assert deployment.deployment_id.startswith("dpl_")
    assert deployment.deployment_url == "https://nyc-petcare-modern.vercel.app"

    # 3. Poll readiness
    ready = await provider.poll_deployment_ready(deployment.deployment_id)
    assert ready.status == "READY"
    assert ready.is_live is True

    # 4. Production URL verification
    verification = await provider.verify_production_url(ready.deployment_url)
    assert verification.is_live is True
    assert verification.status_code == 200
    assert verification.has_html_content is True
    assert verification.response_time_ms > 0
