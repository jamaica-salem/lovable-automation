"""Application configuration and runtime settings."""

import os
from pathlib import Path
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    """Central settings for the automation platform."""

    app_name: str = "Lovable Website Automation Platform"
    app_version: str = "0.1.0"
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1"))

    # Server settings
    host: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8080")))

    # Database settings
    database_path: Path = Field(
        default_factory=lambda: Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "jobs.db")))
    )
    sqlite_busy_timeout_ms: int = 5000

    # Worker concurrency & intervals
    # Design worker runs concurrently and works ahead
    design_worker_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("DESIGN_WORKER_CONCURRENCY", "3"))
    )
    design_poll_interval: float = 2.0

    # Lovable worker concurrency MUST be strictly 1
    lovable_worker_concurrency: int = 1
    lovable_poll_interval: float = 2.0
    skip_blocked_jobs: bool = Field(
        default_factory=lambda: os.getenv("SKIP_BLOCKED_JOBS", "false").lower() in ("true", "1")
    )

    # Vercel worker concurrency (non-blocking)
    vercel_worker_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("VERCEL_WORKER_CONCURRENCY", "2"))
    )
    vercel_poll_interval: float = 3.0

    # Performance targets (benchmarks only, not fake timers)
    target_job_duration_minutes: int = 10
    target_daily_throughput: int = 40
    max_retries: int = 3

    # API Keys / External Services (placeholders for Chunk 2+)
    lovable_api_key: str = Field(default_factory=lambda: os.getenv("LOVABLE_API_KEY", ""))
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    vercel_token: str = Field(default_factory=lambda: os.getenv("VERCEL_TOKEN", ""))
    dribbble_client_id: str = Field(default_factory=lambda: os.getenv("DRIBBBLE_CLIENT_ID", ""))


settings = Settings()
