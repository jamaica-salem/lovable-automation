"""GitHub coordination service."""

from app.config import settings
from services.github.connection import (
    GitHubConnectionProvider,
    MockGitHubConnectionProvider,
    OfficialApiGitHubConnectionProvider,
    WorkspaceNotConnectedError,
)
from services.github.interface import GitHubService as BaseGitHubService
from services.github.models import GitHubRepoInfo, GitHubSyncStatus


class GitHubService(BaseGitHubService):
    """High-level GitHub service managing project connection and sync verification."""

    def __init__(self, connection_provider: Optional[GitHubConnectionProvider] = None):
        if connection_provider is not None:
            self.provider = connection_provider
        elif settings.github_token:
            self.provider = OfficialApiGitHubConnectionProvider()
        else:
            self.provider = MockGitHubConnectionProvider()


    async def connect_and_sync(
        self, lovable_project_id: str, repo_name: str, org: Optional[str] = None
    ) -> GitHubSyncStatus:
        """Connect Lovable project to GitHub repository and wait for commit sync."""
        repo_info = await self.provider.connect_project_to_github(
            lovable_project_id=lovable_project_id,
            repo_name=repo_name,
            org=org,
        )
        return await self.provider.wait_for_repo_sync(repo_info.repo_url)

    async def verify_sync(self, repo_url: str) -> GitHubSyncStatus:
        """Verify repository exists and has received the code export."""
        return await self.provider.wait_for_repo_sync(repo_url)
