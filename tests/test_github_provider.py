"""Tests for GitHub connection provider and repository synchronization."""

import pytest
from services.github.connection import (
    MockGitHubConnectionProvider,
    WorkspaceNotConnectedError,
)
from services.github.service import GitHubService


@pytest.mark.asyncio
async def test_workspace_not_connected_raises_actionable_error():
    provider = MockGitHubConnectionProvider(workspace_connected=False)
    assert await provider.is_workspace_connected() is False

    with pytest.raises(WorkspaceNotConnectedError) as exc_info:
        await provider.connect_project_to_github("proj_123", "nyc-petcare-modern")

    assert "Lovable workspace is not connected to GitHub" in str(exc_info.value)
    assert "OAuth authorization" in str(exc_info.value)


@pytest.mark.asyncio
async def test_successful_github_connection_and_sync_verification():
    provider = MockGitHubConnectionProvider(workspace_connected=True)
    service = GitHubService(connection_provider=provider)

    status = await service.connect_and_sync(
        lovable_project_id="proj_nyc_petcare",
        repo_name="nyc-petcare-modern",
        org="test-org",
    )

    assert status.is_ready is True
    assert status.latest_commit.startswith("sha_")
    assert "nyc-petcare-modern" in status.repo_url
    assert status.commit_count > 0
