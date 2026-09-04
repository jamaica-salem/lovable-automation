"""Orchestrator control and worker fleet status API routes."""

from fastapi import APIRouter, HTTPException
from database.repository import JobRepository
from workers.manager import get_worker_manager

router = APIRouter(prefix="/api/orchestrator", tags=["Orchestrator"])
repo = JobRepository()


@router.get("/status")
def get_orchestrator_status():
    """Retrieve health, active Lovable job, buffer status, and worker statuses."""
    manager = get_worker_manager()
    health = manager.get_health()
    active_job = repo.get_active_lovable_job()
    buffer_jobs = repo.get_ready_buffer_jobs(limit=5)
    worker_statuses = manager.get_status()

    return {
        "health": health,
        "active_lovable_job": active_job.model_dump() if active_job else None,
        "ready_buffer_jobs": [j.model_dump() for j in buffer_jobs],
        "workers": worker_statuses,
    }


@router.post("/start")
async def start_all():
    """Start all worker loops across the pipeline."""
    manager = get_worker_manager()
    await manager.start_all()
    return {"message": "All workers started successfully", "is_running": manager.is_running}


@router.post("/pause")
async def pause_all():
    """Pause all workers."""
    manager = get_worker_manager()
    await manager.pause_all()
    return {"message": "All workers paused", "is_paused": manager.is_paused}


@router.post("/resume")
async def resume_all():
    """Resume all paused workers."""
    manager = get_worker_manager()
    await manager.resume_all()
    return {"message": "All workers resumed", "is_paused": manager.is_paused}


@router.post("/stop")
async def stop_all():
    """Gracefully stop all worker loops."""
    manager = get_worker_manager()
    await manager.stop_all()
    return {"message": "All workers stopped", "is_running": manager.is_running}


@router.post("/workers/{worker_type}/{action}")
async def control_worker_pool(worker_type: str, action: str):
    """Control individual worker pools (design, lovable, vercel) with actions (start, pause, resume, stop)."""
    manager = get_worker_manager()
    worker_type = worker_type.lower()
    action = action.lower()

    valid_types = ("design", "lovable", "vercel")
    valid_actions = ("start", "pause", "resume", "stop")

    if worker_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid worker_type '{worker_type}'. Must be one of {valid_types}")
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action '{action}'. Must be one of {valid_actions}")

    method_name = f"{action}_{worker_type}"
    method = getattr(manager, method_name, None)
    if not method:
        raise HTTPException(status_code=500, detail=f"Handler {method_name} not found on orchestrator")

    import inspect
    if inspect.iscoroutinefunction(method):
        await method()
    else:
        method()

    return {"message": f"Executed {action} on {worker_type} worker pool successfully"}
