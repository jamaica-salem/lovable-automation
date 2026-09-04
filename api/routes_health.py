"""Health check and worker telemetry API routes."""

from fastapi import APIRouter
from utils.timestamps import now_iso
from workers.manager import get_worker_manager

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("/workers")
def get_workers_health():
    """Return explicit health status and heartbeat for Design, Lovable, and Vercel worker pools."""
    manager = get_worker_manager()
    health_data = manager.get_health()
    workers = health_data.get("workers", {})
    watchdog = health_data.get("watchdog", {})

    return {
        "status": health_data.get("health_status", "healthy"),
        "timestamp": now_iso(),
        "workers": {
            "design": {
                "status": workers.get("design", {}).get("status", "healthy"),
                "healthy": workers.get("design", {}).get("healthy", True),
                "last_heartbeat": workers.get("design", {}).get("last_heartbeat"),
                "running_count": workers.get("design", {}).get("running", 0),
                "total_count": workers.get("design", {}).get("total", 0),
            },
            "lovable": {
                "status": workers.get("lovable", {}).get("status", "healthy"),
                "healthy": workers.get("lovable", {}).get("healthy", True),
                "last_heartbeat": workers.get("lovable", {}).get("last_heartbeat"),
                "running_count": workers.get("lovable", {}).get("running", 0),
                "total_count": workers.get("lovable", {}).get("total", 0),
            },
            "vercel": {
                "status": workers.get("vercel", {}).get("status", "healthy"),
                "healthy": workers.get("vercel", {}).get("healthy", True),
                "last_heartbeat": workers.get("vercel", {}).get("last_heartbeat"),
                "running_count": workers.get("vercel", {}).get("running", 0),
                "total_count": workers.get("vercel", {}).get("total", 0),
            },
        },
        "watchdog": {
            "status": watchdog.get("status", "inactive"),
            "runs_count": watchdog.get("runs_count", 0),
            "last_run_at": watchdog.get("last_run_at"),
            "total_recovered": watchdog.get("total_recovered", 0),
        },
    }
