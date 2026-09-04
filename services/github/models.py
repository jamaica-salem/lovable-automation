"""GitHub service models and schemas."""

from typing import Optional
from pydantic import BaseModel, Field
from utils.timestamps import now_iso


class GitHubRepoInfo(BaseModel):
    """GitHub repository details connected to a Lovable project."""

    repo_name: str
    repo_url: str
    owner: str
    default_branch: str = "main"
    created_at: str = Field(default_factory=now_iso)


class GitHubSyncStatus(BaseModel):
    """Synchronization status and commit readiness of a GitHub repository."""

    repo_url: str
    is_ready: bool
    latest_commit: str = ""
    commit_count: int = 0
    error_message: str = ""
    synced_at: str = Field(default_factory=now_iso)
