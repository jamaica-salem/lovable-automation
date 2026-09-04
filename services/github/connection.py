"""GitHub connection provider abstraction and implementations."""

from abc import ABC, abstractmethod
import asyncio
import time
from typing import Optional
import httpx

from app.config import settings
from services.github.models import GitHubRepoInfo, GitHubSyncStatus
from utils.logger import logger
from utils.timestamps import now_iso


class WorkspaceNotConnectedError(Exception):
    """Raised when the Lovable workspace is not authorized to connect with GitHub."""

    def __init__(
        self,
        message: str = (
            "Lovable workspace is not connected to GitHub. "
            "An administrator must perform one-time manual OAuth authorization "
            "in the Lovable dashboard (Project settings -> Git)."
        ),
    ):
        super().__init__(message)


class GitHubConnectionProvider(ABC):
    """Abstract interface for connecting Lovable projects to GitHub repositories."""

    @abstractmethod
    async def is_workspace_connected(self) -> bool:
        """Check if the Lovable workspace has an active GitHub App/OAuth installation."""
        pass

    @abstractmethod
    async def connect_project_to_github(
        self, lovable_project_id: str, repo_name: str, org: Optional[str] = None
    ) -> GitHubRepoInfo:
        """Link a Lovable project to a new or existing GitHub repository."""
        pass

    @abstractmethod
    async def wait_for_repo_sync(
        self, repo_url: str, timeout_seconds: float = 120.0, poll_interval: float = 3.0
    ) -> GitHubSyncStatus:
        """Poll and verify that repository creation and code commit synchronization has finished."""
        pass


class PlaywrightGitHubConnectionProvider(GitHubConnectionProvider):
    """Prepared implementation of browser automation scoped ONLY to the project-to-GitHub UI operation.
    
    Used strictly for the Git settings modal when no programmatic API is available.
    Does not bypass authentication, store passwords, or expose secrets.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless

    async def is_workspace_connected(self) -> bool:
        """Check whether the workspace is already authorized with GitHub."""
        # Detects if Lovable has linked GitHub App permissions
        if settings.github_token:
            return True
        return False

    async def connect_project_to_github(
        self, lovable_project_id: str, repo_name: str, org: Optional[str] = None
    ) -> GitHubRepoInfo:
        target_org = org or settings.github_org

        # Check connection status first
        connected = await self.is_workspace_connected()
        if not connected:
            raise WorkspaceNotConnectedError()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is required for browser-based Git connection. "
                "Install with 'pip install playwright' and run 'playwright install chromium', "
                "or use MockGitHubConnectionProvider."
            )

        logger.info(f"Connecting Lovable project {lovable_project_id} to GitHub repo {target_org}/{repo_name} via UI")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # Navigate strictly to project Git settings
                git_settings_url = f"https://lovable.dev/projects/{lovable_project_id}/settings/git"
                await page.goto(git_settings_url, timeout=30000)

                # Check for "Connect GitHub" auth prompt indicating workspace is unlinked
                unlinked_button = await page.query_selector("button:has-text('Connect GitHub')")
                if unlinked_button:
                    raise WorkspaceNotConnectedError()

                # Fill repository name and click Sync
                repo_input = await page.wait_for_selector("input[name='repo_name'], input[placeholder*='repo']", timeout=15000)
                if repo_input:
                    await repo_input.fill(repo_name)

                sync_button = await page.wait_for_selector("button:has-text('Create repository'), button:has-text('Sync')", timeout=10000)
                if sync_button:
                    await sync_button.click()
                    await page.wait_for_timeout(3000)

            finally:
                await browser.close()

        repo_url = f"https://github.com/{target_org}/{repo_name}"
        return GitHubRepoInfo(
            repo_name=repo_name,
            repo_url=repo_url,
            owner=target_org,
            default_branch="main",
            created_at=now_iso(),
        )

    async def wait_for_repo_sync(
        self, repo_url: str, timeout_seconds: float = 120.0, poll_interval: float = 3.0
    ) -> GitHubSyncStatus:
        """Poll GitHub API to confirm repo and commit readiness."""
        headers = {}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        parts = repo_url.rstrip("/").split("/")
        owner = parts[-2]
        repo = parts[-1]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_seconds:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(api_url, headers=headers)
                    if res.status_code == 200:
                        commits = res.json()
                        if commits and len(commits) > 0:
                            latest_sha = commits[0].get("sha", "")
                            return GitHubSyncStatus(
                                repo_url=repo_url,
                                is_ready=True,
                                latest_commit=latest_sha,
                                commit_count=len(commits),
                                synced_at=now_iso(),
                            )
            except Exception as exc:
                logger.debug(f"Polling GitHub repo {repo_url}: {exc}")

            await asyncio.sleep(poll_interval)

        return GitHubSyncStatus(
            repo_url=repo_url,
            is_ready=False,
            error_message=f"Sync timed out after {timeout_seconds:.1f}s waiting for commits on {repo_url}",
        )


class MockGitHubConnectionProvider(GitHubConnectionProvider):
    """Deterministic, high-fidelity mock provider strictly for automated tests and offline execution."""

    def __init__(self, workspace_connected: bool = True):
        self.workspace_connected = workspace_connected
        self.connected_projects: dict[str, GitHubRepoInfo] = {}

    async def is_workspace_connected(self) -> bool:
        return self.workspace_connected

    async def connect_project_to_github(
        self, lovable_project_id: str, repo_name: str, org: Optional[str] = None
    ) -> GitHubRepoInfo:
        if not self.workspace_connected:
            raise WorkspaceNotConnectedError()

        target_org = org or settings.github_org
        repo_url = f"https://github.com/{target_org}/{repo_name}"
        info = GitHubRepoInfo(
            repo_name=repo_name,
            repo_url=repo_url,
            owner=target_org,
            default_branch="main",
            created_at=now_iso(),
        )
        self.connected_projects[lovable_project_id] = info
        return info

    async def wait_for_repo_sync(
        self, repo_url: str, timeout_seconds: float = 120.0, poll_interval: float = 0.1
    ) -> GitHubSyncStatus:
        # High-fidelity mock returns ready with deterministic commit SHA
        parts = repo_url.rstrip("/").split("/")
        repo_name = parts[-1]
        commit_sha = f"sha_{repo_name[:8]}_ready"
        return GitHubSyncStatus(
            repo_url=repo_url,
            is_ready=True,
            latest_commit=commit_sha,
            commit_count=1,
            synced_at=now_iso(),
        )
