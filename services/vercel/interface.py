"""Vercel deployment and verification service interface."""

from abc import ABC, abstractmethod
from pydantic import BaseModel


class VercelDeployment(BaseModel):
    """Vercel deployment result and live URL."""
    deployment_id: str
    deployment_url: str
    status: str
    is_live: bool = False
    http_status_code: int = 200


class VercelService(ABC):
    """Interface for deploying repositories to Vercel and verifying live deployment."""

    @abstractmethod
    async def create_deployment(self, github_repo_url: str, project_name: str) -> VercelDeployment:
        """Trigger deployment of repository to Vercel."""
        pass

    @abstractmethod
    async def verify_deployment(self, deployment_url: str) -> bool:
        """Verify that deployed website returns HTTP 200 and loads successfully."""
        pass


class StubVercelService(VercelService):
    """Stub implementation for foundation chunk."""

    async def create_deployment(self, github_repo_url: str, project_name: str) -> VercelDeployment:
        slug = project_name.lower().replace("_", "-").replace(" ", "-")[:20]
        url = f"https://{slug}.vercel.app"
        return VercelDeployment(
            deployment_id=f"dpl_{slug}",
            deployment_url=url,
            status="READY",
            is_live=True,
            http_status_code=200,
        )

    async def verify_deployment(self, deployment_url: str) -> bool:
        # In real integration, sends real HTTP GET to verify status 200
        return bool(deployment_url.startswith("https://"))
