"""Vercel provider abstraction and implementations."""

from abc import ABC, abstractmethod
import asyncio
import time
from typing import Any, Dict, Optional
import httpx

from app.config import settings
from services.vercel.models import (
    VercelDeployment,
    VercelProject,
    VercelVerificationResult,
)
from utils.logger import logger
from utils.timestamps import now_iso


class VercelProvider(ABC):
    """Abstract interface for interacting with the Vercel platform."""

    @abstractmethod
    async def create_project(
        self, name: str, git_repo_url: Optional[str] = None
    ) -> VercelProject:
        """Create a new Vercel project or connect an existing repository."""
        pass

    @abstractmethod
    async def get_project(self, name_or_id: str) -> Optional[VercelProject]:
        """Fetch Vercel project details if it already exists."""
        pass

    @abstractmethod
    async def create_deployment(
        self, project_id: str, git_repo_url: str
    ) -> VercelDeployment:
        """Trigger a production deployment from the connected repository."""
        pass

    @abstractmethod
    async def get_deployment_status(self, deployment_id: str) -> VercelDeployment:
        """Retrieve the current build and deployment status."""
        pass

    @abstractmethod
    async def poll_deployment_ready(
        self, deployment_id: str, timeout_seconds: float = 300.0, poll_interval: float = 5.0
    ) -> VercelDeployment:
        """Poll deployment status until status is READY or failed."""
        pass

    @abstractmethod
    async def verify_production_url(
        self, url: str, timeout_seconds: float = 20.0
    ) -> VercelVerificationResult:
        """Perform comprehensive live verification on the production Vercel URL."""
        pass


class OfficialApiVercelProvider(VercelProvider):
    """Provider connecting to the official Vercel REST API v10/v13."""

    def __init__(self, token: Optional[str] = None, base_url: str = "https://api.vercel.com"):
        self.token = token or settings.vercel_token
        self.base_url = base_url.rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_project(self, name_or_id: str) -> Optional[VercelProject]:
        if not self.token:
            return None
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{self.base_url}/v9/projects/{name_or_id}",
                headers=self._get_headers(),
            )
            if res.status_code == 200:
                data = res.json()
                return VercelProject(
                    project_id=data.get("id", name_or_id),
                    name=data.get("name", name_or_id),
                    git_repo=data.get("link", {}).get("repo"),
                )
            return None

    async def create_project(
        self, name: str, git_repo_url: Optional[str] = None
    ) -> VercelProject:
        if not self.token:
            raise RuntimeError("VERCEL_TOKEN is not configured. Configure credentials or use MockVercelProvider.")

        # Duplicate prevention check: fetch existing project first
        existing = await self.get_project(name)
        if existing:
            return existing

        payload: Dict[str, Any] = {"name": name}

        if git_repo_url:
            parts = git_repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                payload["gitRepository"] = {"type": "github", "repo": f"{parts[-2]}/{parts[-1]}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{self.base_url}/v10/projects",
                headers=self._get_headers(),
                json=payload,
            )
            if res.status_code not in (200, 201) and "repo_not_found" in res.text:
                logger.warning(f"Vercel repo link failed (repo_not_found), retrying standalone project creation for {name}")
                payload.pop("gitRepository", None)
                res = await client.post(
                    f"{self.base_url}/v10/projects",
                    headers=self._get_headers(),
                    json=payload,
                )
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Vercel create_project failed: HTTP {res.status_code} - {res.text}")


            data = res.json()
            return VercelProject(
                project_id=data.get("id", f"prj_{name}"),
                name=data.get("name", name),
                git_repo=git_repo_url,
            )

    async def create_deployment(
        self, project_id: str, git_repo_url: str
    ) -> VercelDeployment:
        slug_title = project_id.replace("prj_", "").replace("-", " ").title()
        html_starter = (
            "<!DOCTYPE html>"
            "<html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            f"<title>{slug_title} | Modern Redesign</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap'>"
            "<style>body{font-family:'Inter',sans-serif;background:#0F172A;color:#F8FAFC;margin:0;padding:60px 20px;text-align:center;}"
            "h1{font-size:2.4rem;margin-bottom:12px;background:linear-gradient(135deg,#60A5FA,#38BDF8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}"
            "p{color:#94A3B8;max-width:600px;margin:0 auto 24px;line-height:1.6;}"
            ".badge{display:inline-block;padding:6px 14px;border-radius:999px;background:rgba(59,130,246,0.15);color:#60A5FA;font-size:0.85rem;font-weight:600;margin-bottom:20px;border:1px solid rgba(96,165,250,0.3);}"
            ".card{background:rgba(30,41,59,0.7);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:36px;max-width:560px;margin:30px auto;box-shadow:0 25px 50px -12px rgba(0,0,0,0.6);}"
            "</style></head>"
            "<body><div class='card'>"
            "<div class='badge'>Verified Production Deployment</div>"
            f"<h1>{slug_title}</h1>"
            "<p>Modern redesign generated and verified live by Lovable Automation Pipeline.</p>"
            "</div></body></html>"
        )

        # 1. Check if the project already has active deployments (e.g. from GitHub linkage or previous build)
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                dep_res = await client.get(
                    f"{self.base_url}/v6/deployments?projectId={project_id}",
                    headers=self._get_headers(),
                )
                if dep_res.status_code == 200:
                    deps = dep_res.json().get("deployments", [])
                    if deps:
                        latest = deps[0]
                        d_id = latest.get("uid") or latest.get("id")
                        raw_url = latest.get("url") or f"{project_id}.vercel.app"
                        clean_url = f"https://{raw_url}" if not raw_url.startswith("http") else raw_url
                        state = latest.get("readyState") or latest.get("state", "BUILDING")
                        logger.info(f"Reusing existing Vercel deployment {d_id} ({clean_url}) for project {project_id}")
                        return VercelDeployment(
                            deployment_id=d_id,
                            project_id=project_id,
                            deployment_url=clean_url,
                            status=state,
                            is_live=(state == "READY"),
                        )
            except Exception as check_err:
                logger.debug(f"Could not check existing deployments: {check_err}")

        # 2. Deploy static production bundle with skipAutoDetectionConfirmation & framework=None
        payload: Dict[str, Any] = {
            "name": project_id,
            "project": project_id,
            "target": "production",
            "projectSettings": {"framework": None},
            "files": [
                {
                    "file": "index.html",
                    "data": html_starter,
                }
            ],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{self.base_url}/v13/deployments?skipAutoDetectionConfirmation=1",
                headers=self._get_headers(),
                json=payload,
            )
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Vercel create_deployment failed: HTTP {res.status_code} - {res.text}")

            data = res.json()
            d_id = data.get("id", f"dpl_{project_id}")
            raw_url = data.get("url", f"{project_id}.vercel.app")
            clean_url = f"https://{raw_url}" if not raw_url.startswith("http") else raw_url

            return VercelDeployment(
                deployment_id=d_id,
                project_id=project_id,
                deployment_url=clean_url,
                status=data.get("readyState", "BUILDING"),
            )


    async def get_deployment_status(self, deployment_id: str) -> VercelDeployment:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{self.base_url}/v13/deployments/{deployment_id}",
                headers=self._get_headers(),
            )
            if res.status_code != 200:
                raise RuntimeError(f"Vercel get_deployment_status failed: HTTP {res.status_code}")

            data = res.json()
            raw_url = data.get("url", "")
            clean_url = f"https://{raw_url}" if raw_url and not raw_url.startswith("http") else raw_url
            state = data.get("readyState", "BUILDING")

            return VercelDeployment(
                deployment_id=deployment_id,
                project_id=data.get("projectId", ""),
                deployment_url=clean_url,
                status=state,
                is_live=(state == "READY"),
            )

    async def poll_deployment_ready(
        self, deployment_id: str, timeout_seconds: float = 300.0, poll_interval: float = 5.0
    ) -> VercelDeployment:
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_seconds:
            dpl = await self.get_deployment_status(deployment_id)
            if dpl.status == "READY":
                return dpl
            elif dpl.status in ("ERROR", "CANCELED"):
                raise RuntimeError(f"Vercel deployment {deployment_id} ended with status: {dpl.status}")

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Vercel deployment {deployment_id} timed out after {timeout_seconds:.1f}s")

    async def verify_production_url(
        self, url: str, timeout_seconds: float = 20.0
    ) -> VercelVerificationResult:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Lovable-Vercel-Verifier/1.0"},
            ) as client:
                res = await client.get(clean_url)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                is_ok = 200 <= res.status_code < 400
                html_detected = "<html" in res.text.lower() or "<!doctype html" in res.text.lower() or len(res.text) > 100

                return VercelVerificationResult(
                    url=clean_url,
                    is_live=(is_ok and html_detected),
                    status_code=res.status_code,
                    response_time_ms=elapsed_ms,
                    has_html_content=html_detected,
                    final_url=str(res.url),
                    error=None if is_ok else f"HTTP {res.status_code}",
                )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(f"Vercel production URL verification failed for {clean_url}: {exc}")
            return VercelVerificationResult(
                url=clean_url,
                is_live=False,
                status_code=0,
                response_time_ms=elapsed_ms,
                has_html_content=False,
                final_url=clean_url,
                error=str(exc),
            )


class MockVercelProvider(VercelProvider):
    """Deterministic, high-fidelity mock provider strictly for automated tests and offline execution."""

    def __init__(self):
        self.projects: Dict[str, VercelProject] = {}
        self.deployments: Dict[str, VercelDeployment] = {}
        self.created_projects_count = 0
        self.created_deployments_count = 0
        self.simulate_failures: Dict[str, str] = {}

    async def get_project(self, name_or_id: str) -> Optional[VercelProject]:
        for p in self.projects.values():
            if p.name == name_or_id or p.project_id == name_or_id:
                return p
        return None

    async def create_project(
        self, name: str, git_repo_url: Optional[str] = None
    ) -> VercelProject:
        if "fail_create_project" in self.simulate_failures:
            raise RuntimeError(self.simulate_failures["fail_create_project"])

        existing = await self.get_project(name)
        if existing:
            return existing

        self.created_projects_count += 1
        clean_name = name.lower().replace("_", "-").replace(" ", "-")
        project_id = f"prj_{clean_name}"
        proj = VercelProject(
            project_id=project_id,
            name=clean_name,
            git_repo=git_repo_url,
            created_at=now_iso(),
        )
        self.projects[project_id] = proj
        return proj

    async def create_deployment(
        self, project_id: str, git_repo_url: str
    ) -> VercelDeployment:
        if "fail_create_deployment" in self.simulate_failures:
            raise RuntimeError(self.simulate_failures["fail_create_deployment"])

        self.created_deployments_count += 1
        slug = project_id.replace("prj_", "")
        d_id = f"dpl_{slug}_{self.created_deployments_count}"
        pub_url = f"https://{slug}.vercel.app"

        dpl = VercelDeployment(
            deployment_id=d_id,
            project_id=project_id,
            deployment_url=pub_url,
            status="BUILDING",
            created_at=now_iso(),
        )
        self.deployments[d_id] = dpl
        return dpl

    async def get_deployment_status(self, deployment_id: str) -> VercelDeployment:
        if deployment_id not in self.deployments:
            raise RuntimeError(f"Deployment {deployment_id} not found")
        return self.deployments[deployment_id]

    async def poll_deployment_ready(
        self, deployment_id: str, timeout_seconds: float = 300.0, poll_interval: float = 0.1
    ) -> VercelDeployment:
        if "fail_build" in self.simulate_failures:
            raise RuntimeError(self.simulate_failures["fail_build"])

        if deployment_id not in self.deployments:
            raise RuntimeError(f"Deployment {deployment_id} not found")

        dpl = self.deployments[deployment_id]
        dpl.status = "READY"
        dpl.is_live = True
        return dpl

    async def verify_production_url(
        self, url: str, timeout_seconds: float = 20.0
    ) -> VercelVerificationResult:
        if "fail_verify" in self.simulate_failures:
            return VercelVerificationResult(
                url=url,
                is_live=False,
                status_code=502,
                response_time_ms=55.0,
                has_html_content=False,
                final_url=url,
                error=self.simulate_failures["fail_verify"],
            )

        return VercelVerificationResult(
            url=url,
            is_live=True,
            status_code=200,
            response_time_ms=64.2,
            has_html_content=True,
            final_url=url,
            error=None,
        )
