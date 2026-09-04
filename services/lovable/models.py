"""Lovable service models and schemas."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from utils.timestamps import now_iso


class LovableProject(BaseModel):
    """Lovable project representation."""

    project_id: str
    project_name: str
    status: str = "created"
    editor_url: str = ""
    preview_url: str = ""
    published_url: Optional[str] = None
    prompt: str = ""
    created_at: str = Field(default_factory=now_iso)
    deduplicated: bool = False


class LovableMessage(BaseModel):
    """Lovable agent message execution result."""

    message_id: str
    thread_id: Optional[str] = None
    project_id: str
    status: str = "completed"
    content: str = ""
    diff_summary: str = ""


class LovableDeployment(BaseModel):
    """Published deployment on lovable.app."""

    project_id: str
    published_url: str
    deployed_at: str = Field(default_factory=now_iso)
    status: str = "deployed"
    version: str = "v1.0.0"


class UrlVerificationResult(BaseModel):
    """Live verification of published lovable.app deployment."""

    url: str
    status_code: int = 0
    response_time_ms: float = 0.0
    is_reachable: bool = False
    verified_at: str = Field(default_factory=now_iso)
    error: Optional[str] = None
