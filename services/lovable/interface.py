"""Lovable service interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class LovableProject(BaseModel):
    """Lovable project state and identifiers."""
    project_id: str
    project_name: str
    status: str
    prompt: str


class LovablePublishResult(BaseModel):
    """Published URL result from Lovable."""
    project_id: str
    published_url: str
    version: str


class LovableGitHubExportResult(BaseModel):
    """GitHub repository export result from Lovable."""
    project_id: str
    github_repo_url: str
    branch: str = "main"


class LovableService(ABC):
    """Interface for Lovable operations (Chunk 1 architectural foundation).
    
    Subsequent chunks will connect to official APIs, MCP tools, or validated browser automation.
    """

    @abstractmethod
    async def create_project(self, name: str, prompt: str) -> LovableProject:
        """Initialize a new redesign project in Lovable."""
        pass

    @abstractmethod
    async def submit_prompt_and_generate(self, project_id: str, prompt: str) -> bool:
        """Submit the structured redesign prompt and await generation."""
        pass

    @abstractmethod
    async def verify_generation_completed(self, project_id: str) -> bool:
        """Verify that generation has legitimately finished with no fatal build errors."""
        pass

    @abstractmethod
    async def publish_project(self, project_id: str) -> LovablePublishResult:
        """Publish the project and return live lovable.app URL."""
        pass

    @abstractmethod
    async def export_to_github(self, project_id: str, repo_name: str) -> LovableGitHubExportResult:
        """Trigger Lovable's GitHub synchronization / repo export."""
        pass


class StubLovableService(LovableService):
    """Stub implementation for foundation chunk."""

    async def create_project(self, name: str, prompt: str) -> LovableProject:
        return LovableProject(
            project_id=f"lovable_proj_{name.lower().replace(' ', '_')[:16]}",
            project_name=name,
            status="created",
            prompt=prompt,
        )

    async def submit_prompt_and_generate(self, project_id: str, prompt: str) -> bool:
        return True

    async def verify_generation_completed(self, project_id: str) -> bool:
        return True

    async def publish_project(self, project_id: str) -> LovablePublishResult:
        return LovablePublishResult(
            project_id=project_id,
            published_url=f"https://{project_id}.lovable.app",
            version="v1.0.0",
        )

    async def export_to_github(self, project_id: str, repo_name: str) -> LovableGitHubExportResult:
        return LovableGitHubExportResult(
            project_id=project_id,
            github_repo_url=f"https://github.com/organization/{repo_name}",
            branch="main",
        )
