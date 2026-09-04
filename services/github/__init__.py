"""GitHub integration package."""

from services.github.connection import (
    GitHubConnectionProvider,
    MockGitHubConnectionProvider,
    PlaywrightGitHubConnectionProvider,
    WorkspaceNotConnectedError,
)
from services.github.interface import (
    GitHubService as BaseGitHubService,
    StubGitHubService,
)
from services.github.models import GitHubRepoInfo, GitHubSyncStatus
from services.github.service import GitHubService

__all__ = [
    "GitHubRepoInfo",
    "GitHubSyncStatus",
    "GitHubConnectionProvider",
    "PlaywrightGitHubConnectionProvider",
    "MockGitHubConnectionProvider",
    "WorkspaceNotConnectedError",
    "BaseGitHubService",
    "StubGitHubService",
    "GitHubService",
]
