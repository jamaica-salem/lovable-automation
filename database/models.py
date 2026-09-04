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


class GitHubStatus(str, Enum):
    """Lifecycle states for GitHub Synchronization."""
    GITHUB_PENDING = "GITHUB_PENDING"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
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
    queue_position: int = 1
    business_name: Optional[str] = None
    project_slug: Optional[str] = None
    original_csv_row: Dict[str, Any] = Field(default_factory=dict)
    # Backward compatibility alias
    csv_row_index: Optional[int] = None
    input_metadata: Dict[str, Any] = Field(default_factory=dict)


class JobCreate(JobBase):
    """Payload for creating a new job from CSV import."""
    pass


class Job(BaseModel):
    """Full persistent job record matching Chunk 2 specifications."""
    id: Optional[int] = None
    job_uid: str
    queue_position: int
    website_url: str
    business_name: Optional[str] = None
    project_slug: Optional[str] = None
    original_csv_row: Dict[str, Any] = Field(default_factory=dict)

    # State machine dimensions
    overall_status: OverallStatus = OverallStatus.PENDING
    design_status: DesignStatus = DesignStatus.DESIGN_QUEUED
    lovable_status: LovableStatus = LovableStatus.WAITING_FOR_DESIGN
    github_status: GitHubStatus = GitHubStatus.GITHUB_PENDING
    vercel_status: VercelStatus = VercelStatus.VERCEL_QUEUED

    # Design research fields
    design_reference_url: Optional[str] = None
    design_reference_image: Optional[str] = None
    design_reference_title: Optional[str] = None
    design_reference_source: Optional[str] = None
    design_score: Optional[float] = None
    design_reason: Optional[str] = None
    design_error: Optional[str] = None
    design_reference_data: Optional[Dict[str, Any]] = None

    # Lovable fields
    lovable_project_id: Optional[str] = None
    lovable_editor_url: Optional[str] = None
    lovable_preview_url: Optional[str] = None
    lovable_published_url: Optional[str] = None

    # GitHub fields
    github_repository: Optional[str] = None
    github_repository_url: Optional[str] = None
    github_repo_url: Optional[str] = None  # Backward-compatible alias
    github_commit_sha: Optional[str] = None

    # Vercel fields
    vercel_project_id: Optional[str] = None
    vercel_deployment_id: Optional[str] = None
    vercel_url: Optional[str] = None
    vercel_deployment_url: Optional[str] = None  # Backward-compatible alias

    # Overall & error handling
    error_message: Optional[str] = None
    retry_count: int = 0

    # Fine-grained timestamps
    created_at: str
    updated_at: str
    design_started_at: Optional[str] = None
    design_completed_at: Optional[str] = None
    lovable_started_at: Optional[str] = None
    lovable_completed_at: Optional[str] = None
    published_at: Optional[str] = None
    lovable_published_at: Optional[str] = None  # Backward-compatible alias
    github_started_at: Optional[str] = None
    github_completed_at: Optional[str] = None
    github_synced_at: Optional[str] = None      # Backward-compatible alias
    vercel_started_at: Optional[str] = None
    vercel_completed_at: Optional[str] = None
    completed_at: Optional[str] = None
    job_completed_at: Optional[str] = None      # Backward-compatible alias

    # Duration metrics (seconds)
    design_duration_seconds: Optional[float] = None
    lovable_duration_seconds: Optional[float] = None
    lovable_publish_duration_seconds: Optional[float] = None
    github_sync_duration_seconds: Optional[float] = None
    vercel_duration_seconds: Optional[float] = None
    verification_duration_seconds: Optional[float] = None
    total_duration_seconds: Optional[float] = None

    # Legacy field mappings
    csv_row_index: Optional[int] = None
    input_metadata: Dict[str, Any] = Field(default_factory=dict)


class JobEvent(BaseModel):
    """Event log record for state transitions and audit tracking."""
    id: Optional[int] = None
    job_id: int
    event_type: str
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class JobLog(BaseModel):
    """Structured log record linked to a job (legacy compatible)."""
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
    design_ready: int = 0
    waiting_for_lovable: int = 0
    lovable_generating: int = 0
    publishing: int = 0
    github_syncing: int = 0
    vercel_deploying: int = 0
    completed: int = 0
    failed: int = 0

    # Backward-compatible aliases for legacy callers
    lovable_processing: int = 0
    vercel_deployment: int = 0


# Model alias for pipeline callers
RedesignJob = Job
