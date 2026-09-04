"""Job management API routes."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from database.models import Job, JobCreate, JobLog, JobEvent, OverallStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
repo = JobRepository()
queue = PersistentJobQueue(repo)


@router.get("", response_model=List[Job])
def list_jobs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status: Optional[OverallStatus] = None,
):
    """List jobs ordered by original CSV row index."""
    return repo.list_jobs(limit=limit, offset=offset, status=status)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: int):
    """Get full details of a specific job by integer ID."""
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/logs", response_model=List[JobLog])
def get_job_logs(job_id: int):
    """Get audit trail logs for a specific job."""
    return repo.get_job_logs(job_id)


@router.get("/{job_id}/events", response_model=List[JobEvent])
def get_job_events(job_id: int):
    """Get chronological event timeline for a specific job."""
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return repo.get_job_events(job_id)


@router.post("/{job_id}/retry", response_model=Job)
def retry_job(job_id: int):
    """Reset a failed job to clean queued state for automatic retry."""
    job = repo.retry_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or could not be retried")
    return job


@router.post("/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: int):
    """Cancel a pending or active job."""
    job = repo.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("", response_model=Job)
def create_job(payload: JobCreate):
    """Manually enqueue a new website redesign job."""
    return queue.enqueue(
        website_url=payload.website_url,
        csv_row_index=payload.csv_row_index,
        input_metadata=payload.input_metadata,
    )
