"""Vercel service models and schemas."""

from typing import Optional
from pydantic import BaseModel, Field
from utils.timestamps import now_iso


class VercelProject(BaseModel):
    """Vercel project representation."""

    project_id: str
    name: str
    git_repo: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class VercelDeployment(BaseModel):
    """Vercel deployment state and metadata."""

    deployment_id: str
    project_id: str
    deployment_url: str
    status: str = "BUILDING"  # BUILDING, READY, ERROR, CANCELED
    is_live: bool = False
    http_status_code: int = 200
    created_at: str = Field(default_factory=now_iso)


class VercelVerificationResult(BaseModel):
    """Verification result for a deployed Vercel production URL."""

    url: str
    is_live: bool = False
    status_code: int = 0
    response_time_ms: float = 0.0
    has_html_content: bool = False
    final_url: str = ""
    error: Optional[str] = None
    verified_at: str = Field(default_factory=now_iso)
