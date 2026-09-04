"""GitHub synchronization service interface."""

from abc import ABC, abstractmethod
from pydantic import BaseModel


class GitHubSyncStatus(BaseModel):
    """Status of GitHub repository sync."""
    repo_url: str
    is_ready: bool
    latest_commit: str = ""
    error_message: str = ""


class GitHubService(ABC):
    """Interface for verifying GitHub sync from Lovable."""

    @abstractmethod
    async def verify_sync(self, repo_url: str) -> GitHubSyncStatus:
        """Verify repository exists and has received the code export."""
        pass


class StubGitHubService(GitHubService):
    """Stub implementation for foundation chunk."""

    async def verify_sync(self, repo_url: str) -> GitHubSyncStatus:
        return GitHubSyncStatus(
            repo_url=repo_url,
            is_ready=True,
            latest_commit="a1b2c3d4e5f6",
        )
