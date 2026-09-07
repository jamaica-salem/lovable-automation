"""Lovable provider abstraction and implementations."""

from abc import ABC, abstractmethod
import asyncio
import time
from typing import Any, Dict, Optional
import httpx

from app.config import settings
from services.lovable.models import (
    LovableDeployment,
    LovableMessage,
    LovableProject,
    UrlVerificationResult,
)
from services.lovable.url_verifier import LovableUrlVerifier
from utils.logger import logger
from utils.timestamps import now_iso


class LovableProvider(ABC):
    """Abstract interface for interacting with the Lovable platform."""

    @abstractmethod
    async def create_project(
        self, project_name: str, initial_message: str, timeout_seconds: float = 120.0
    ) -> LovableProject:
        """Create a new project in Lovable with the initial build prompt."""
        pass

    @abstractmethod
    async def get_project(self, project_id: str) -> LovableProject:
        """Fetch current project state, editor URL, and preview URL."""
        pass

    @abstractmethod
    async def send_message(
        self,
        project_id: str,
        message: str,
        wait: bool = True,
        timeout_seconds: float = 120.0,
    ) -> LovableMessage:
        """Send an agent message to iterate on code or fix layout."""
        pass

    @abstractmethod
    async def poll_completion(
        self, project_id: str, timeout_seconds: float = 300.0, poll_interval: float = 5.0
    ) -> bool:
        """Poll project build status until generation has legitimately completed."""
        pass

    @abstractmethod
    async def deploy_project(
        self, project_id: str, name: Optional[str] = None
    ) -> LovableDeployment:
        """Deploy the project to production on lovable.app."""
        pass

    @abstractmethod
    async def verify_url(
        self, url: str, timeout_seconds: float = 15.0
    ) -> UrlVerificationResult:
        """Verify that the published URL is reachable and returning 200 OK."""
        pass


class OfficialMcpLovableProvider(LovableProvider):
    """Provider connecting to the official Lovable MCP endpoint at https://mcp.lovable.dev."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://mcp.lovable.dev",
        verifier: Optional[LovableUrlVerifier] = None,
    ):
        self.api_key = api_key or settings.lovable_api_key
        self.base_url = base_url.rstrip("/")
        self.verifier = verifier or LovableUrlVerifier()

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["Lovable-API-Key"] = self.api_key
        return headers

    async def create_project(
        self, project_name: str, initial_message: str, timeout_seconds: float = 120.0
    ) -> LovableProject:
        if not self.api_key:
            raise RuntimeError(
                "LOVABLE_API_KEY is not configured. Configure credentials or use MockLovableProvider."
            )

        payload = {
            "initial_message": initial_message,
            "wait": True,
            "timeout_seconds": int(timeout_seconds),
        }
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            res = await client.post(
                f"{self.base_url}/projects",
                headers=self._get_headers(),
                json=payload,
            )
            if res.status_code not in (200, 201):
                raise RuntimeError(
                    f"Failed to create Lovable project: HTTP {res.status_code} - {res.text}"
                )

            data = res.json()
            proj_id = data.get("projectId") or data.get("id") or f"proj_{project_name}"
            return LovableProject(
                project_id=proj_id,
                project_name=project_name,
                status=data.get("status", "generating"),
                editor_url=f"https://lovable.dev/projects/{proj_id}",
                preview_url=data.get("preview_url") or f"https://preview--{proj_id}.lovable.app",
                prompt=initial_message,
                deduplicated=data.get("deduplicated", False),
            )

    async def get_project(self, project_id: str) -> LovableProject:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                f"{self.base_url}/projects/{project_id}",
                headers=self._get_headers(),
            )
            if res.status_code != 200:
                raise RuntimeError(f"Failed to fetch Lovable project {project_id}: HTTP {res.status_code}")

            data = res.json()
            return LovableProject(
                project_id=project_id,
                project_name=data.get("name", project_id),
                status=data.get("status", "ready"),
                editor_url=f"https://lovable.dev/projects/{project_id}",
                preview_url=data.get("preview_url") or f"https://preview--{project_id}.lovable.app",
                published_url=data.get("published_url"),
            )

    async def send_message(
        self,
        project_id: str,
        message: str,
        wait: bool = True,
        timeout_seconds: float = 120.0,
    ) -> LovableMessage:
        payload = {"message": message, "wait": wait, "timeout_seconds": int(timeout_seconds)}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            res = await client.post(
                f"{self.base_url}/projects/{project_id}/messages",
                headers=self._get_headers(),
                json=payload,
            )
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Lovable send_message failed: HTTP {res.status_code}")

            data = res.json()
            return LovableMessage(
                message_id=data.get("message_id", "msg_default"),
                thread_id=data.get("thread_id"),
                project_id=project_id,
                status=data.get("status", "completed"),
                content=data.get("content", ""),
            )

    async def poll_completion(
        self, project_id: str, timeout_seconds: float = 300.0, poll_interval: float = 5.0
    ) -> bool:
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_seconds:
            try:
                proj = await self.get_project(project_id)
                if proj.status in ("ready", "completed", "deployed"):
                    return True
                elif proj.status in ("failed", "error"):
                    return False
            except Exception as exc:
                logger.warning(f"Error polling Lovable project {project_id}: {exc}")

            await asyncio.sleep(poll_interval)
        return False

    async def deploy_project(
        self, project_id: str, name: Optional[str] = None
    ) -> LovableDeployment:
        payload = {"name": name} if name else {}
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{self.base_url}/projects/{project_id}/deploy",
                headers=self._get_headers(),
                json=payload,
            )
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Deploy project failed: HTTP {res.status_code} - {res.text}")

            data = res.json()
            pub_url = data.get("url") or data.get("published_url") or f"https://{name or project_id}.lovable.app"
            return LovableDeployment(
                project_id=project_id,
                published_url=pub_url,
                deployed_at=now_iso(),
            )

    async def verify_url(
        self, url: str, timeout_seconds: float = 15.0
    ) -> UrlVerificationResult:
        return await self.verifier.verify(url)


class MockLovableProvider(LovableProvider):
    """Deterministic, high-fidelity mock provider strictly for testing and offline execution."""

    def __init__(self, verifier: Optional[LovableUrlVerifier] = None):
        self.verifier = verifier or LovableUrlVerifier()
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.generation_ticks: Dict[str, int] = {}
        self.simulate_failures: Dict[str, str] = {}
        self.created_projects_count = 0

    async def create_project(
        self, project_name: str, initial_message: str, timeout_seconds: float = 120.0
    ) -> LovableProject:
        # Check simulated failure
        if "fail_create" in self.simulate_failures:
            raise RuntimeError(self.simulate_failures["fail_create"])

        self.created_projects_count += 1
        clean_slug = project_name.lower().replace(" ", "-").replace("_", "-")
        project_id = f"lovable_proj_{clean_slug}"

        project_data = {
            "project_id": project_id,
            "project_name": project_name,
            "status": "generating",
            "editor_url": f"https://lovable.dev/projects/{project_id}",
            "preview_url": f"https://preview--{project_id}.lovable.app",
            "prompt": initial_message,
            "created_at": now_iso(),
        }
        self.projects[project_id] = project_data
        self.generation_ticks[project_id] = 0

        return LovableProject(**project_data)

    async def get_project(self, project_id: str) -> LovableProject:
        if project_id not in self.projects:
            raise RuntimeError(f"Project {project_id} not found")
        return LovableProject(**self.projects[project_id])

    async def send_message(
        self,
        project_id: str,
        message: str,
        wait: bool = True,
        timeout_seconds: float = 120.0,
    ) -> LovableMessage:
        if project_id not in self.projects:
            raise RuntimeError(f"Project {project_id} not found")

        return LovableMessage(
            message_id=f"msg_{int(time.time()*1000)}",
            project_id=project_id,
            status="completed",
            content="Changes applied successfully.",
        )

    async def poll_completion(
        self, project_id: str, timeout_seconds: float = 300.0, poll_interval: float = 0.1
    ) -> bool:
        if "fail_generation" in self.simulate_failures:
            return False

        if project_id not in self.projects:
            return False

        # Simulate progressive completion
        self.generation_ticks[project_id] = self.generation_ticks.get(project_id, 0) + 1
        self.projects[project_id]["status"] = "ready"
        return True

    async def deploy_project(
        self, project_id: str, name: Optional[str] = None
    ) -> LovableDeployment:
        if "fail_deploy" in self.simulate_failures:
            raise RuntimeError(self.simulate_failures["fail_deploy"])

        if project_id not in self.projects:
            raise RuntimeError(f"Project {project_id} not found")

        slug = name or self.projects[project_id]["project_name"]
        pub_url = f"https://{slug}.lovable.app"
        self.projects[project_id]["published_url"] = pub_url
        self.projects[project_id]["status"] = "deployed"

        return LovableDeployment(
            project_id=project_id,
            published_url=pub_url,
            deployed_at=now_iso(),
        )

    async def verify_url(
        self, url: str, timeout_seconds: float = 15.0
    ) -> UrlVerificationResult:
        if "fail_verify" in self.simulate_failures:
            return UrlVerificationResult(
                url=url,
                status_code=502,
                response_time_ms=45.0,
                is_reachable=False,
                error=self.simulate_failures["fail_verify"],
            )

        # High-fidelity mock verification simulating healthy 200 OK
        return UrlVerificationResult(
            url=url,
            status_code=200,
            response_time_ms=75.5,
            is_reachable=True,
            verified_at=now_iso(),
            error=None,
        )
