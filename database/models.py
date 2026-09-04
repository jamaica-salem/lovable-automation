"""Database models and state definitions for the automation platform."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DesignStatus(str, Enum):
    """Lifecycle states for Design Research."""
    DESIGN_QUEUED = "DESIGN_QUEUED"
    ANALYZING = "ANALYZING"
    SEARCHING = "SEARCHING"
    EVALUATING = "EVALUATING"
    DESIGN_READY = "DESIGN_READY"
    DESIGN_FAILED = "DESIGN_FAILED"
    DESIGN_NEEDS_REVIEW = "DESIGN_NEEDS_REVIEW"


class LovableStatus(str, Enum):
    """Lifecycle states for Lovable Generation and Publishing."""
    WAITING_FOR_DESIGN = "WAITING_FOR_DESIGN"
    PREPARING = "PREPARING"
    SUBMITTING = "SUBMITTING"
    GENERATING = "GENERATING"
    VERIFYING = "VERIFYING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    GITHUB_SYNCING = "GITHUB_SYNCING"
    GITHUB_READY = "GITHUB_READY"
    FAILED = "FAILED"


class VercelStatus(str, Enum):
    """Lifecycle states for Vercel Deployment and Verification."""
    VERCEL_QUEUED = "VERCEL_QUEUED"
    DEPLOYING = "DEPLOYING"
    VERIFYING = "VERIFYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"


class OverallStatus(str, Enum):
    """Overall high-level lifecycle status of a job."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class JobBase(BaseModel):
    """Base job schema containing common fields."""
    website_url: str
    csv_row_index: int
    input_metadata: Dict[str, Any] = Field(default_factory=dict)


class JobCreate(JobBase):
    """Payload for creating a new job from CSV import."""
    pass


class Job(BaseModel):
    """Full persistent job record."""
    id: Optional[int] = None
    job_uid: str
    csv_row_index: int
    website_url: str
    input_metadata: Dict[str, Any] = Field(default_factory=dict)

    # State machine dimensions (never collapsed)
    overall_status: OverallStatus = OverallStatus.PENDING
    design_status: DesignStatus = DesignStatus.DESIGN_QUEUED
    lovable_status: LovableStatus = LovableStatus.WAITING_FOR_DESIGN
    vercel_status: VercelStatus = VercelStatus.VERCEL_QUEUED

    # Artifacts and outputs
    design_reference_data: Optional[Dict[str, Any]] = None
    lovable_project_id: Optional[str] = None
    lovable_published_url: Optional[str] = None
    github_repo_url: Optional[str] = None
    vercel_deployment_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0

    # Fine-grained timestamps for duration tracking
    created_at: str
    updated_at: str
    design_started_at: Optional[str] = None
    design_completed_at: Optional[str] = None
    lovable_started_at: Optional[str] = None
    lovable_completed_at: Optional[str] = None
    lovable_published_at: Optional[str] = None
    github_synced_at: Optional[str] = None
    vercel_started_at: Optional[str] = None
    vercel_completed_at: Optional[str] = None
    verification_started_at: Optional[str] = None
    verification_completed_at: Optional[str] = None
    job_completed_at: Optional[str] = None

    # Calculated durations in seconds
    design_duration_seconds: Optional[float] = None
    lovable_duration_seconds: Optional[float] = None
    lovable_publish_duration_seconds: Optional[float] = None
    github_sync_duration_seconds: Optional[float] = None
    vercel_duration_seconds: Optional[float] = None
    verification_duration_seconds: Optional[float] = None
    total_duration_seconds: Optional[float] = None


class JobLog(BaseModel):
    """Structured log record linked to a job."""
    id: Optional[int] = None
    job_id: int
    job_uid: str
    stage: str
    level: str = "INFO"
    message: str
    created_at: str


class PipelineStats(BaseModel):
    """Dashboard statistics reflecting distinct pipeline stages."""
    total_jobs: int = 0
    pending: int = 0
    design_research: int = 0
    waiting_for_lovable: int = 0
    lovable_processing: int = 0
    vercel_deployment: int = 0
    completed: int = 0
    failed: int = 0
