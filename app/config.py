"""Application configuration and runtime settings."""

import os
from pathlib import Path
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(env_path: Path) -> None:
    """Load key-value pairs from .env into os.environ if not already set."""
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                # Keep existing environment variables, otherwise set from .env
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_env_file(BASE_DIR / ".env")


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
    # Design worker runs concurrently and works ahead (default: 2)
    design_worker_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("DESIGN_WORKER_CONCURRENCY", "2"))
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

    # Design Research Worker Settings
    design_buffer_size: int = Field(
        default_factory=lambda: int(os.getenv("DESIGN_BUFFER_SIZE", "3"))
    )
    design_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("DESIGN_TIMEOUT_SECONDS", "75.0"))
    )

    # Lovable Worker Settings
    lovable_generation_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("LOVABLE_GENERATION_TIMEOUT_SECONDS", "300.0"))
    )
    lovable_publish_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("LOVABLE_PUBLISH_TIMEOUT_SECONDS", "120.0"))
    )
    lovable_verify_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("LOVABLE_VERIFY_TIMEOUT_SECONDS", "15.0"))
    )

    # GitHub Handoff Settings
    github_org: str = Field(default_factory=lambda: os.getenv("GITHUB_ORG", "organization"))
    github_sync_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("GITHUB_SYNC_TIMEOUT_SECONDS", "120.0"))
    )

    # Vercel Worker Settings
    vercel_deploy_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("VERCEL_DEPLOY_TIMEOUT_SECONDS", "300.0"))
    )
    vercel_verify_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("VERCEL_VERIFY_TIMEOUT_SECONDS", "20.0"))
    )

    # Orchestrator & Health Settings
    stale_job_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("STALE_JOB_TIMEOUT_SECONDS", "600.0"))
    )
    watchdog_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("WATCHDOG_INTERVAL_SECONDS", "30.0"))
    )
    exponential_backoff_base_seconds: float = Field(
        default_factory=lambda: float(os.getenv("EXPONENTIAL_BACKOFF_BASE_SECONDS", "2.0"))
    )

    # API Keys / External Services
    lovable_api_key: str = Field(default_factory=lambda: os.getenv("LOVABLE_API_KEY", ""))
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    vercel_token: str = Field(default_factory=lambda: os.getenv("VERCEL_TOKEN", ""))
    dribbble_client_id: str = Field(default_factory=lambda: os.getenv("DRIBBBLE_CLIENT_ID", ""))
    dribbble_access_token: str = Field(default_factory=lambda: os.getenv("DRIBBBLE_ACCESS_TOKEN", ""))


settings = Settings()
