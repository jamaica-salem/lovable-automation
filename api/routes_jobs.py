"""Job management API routes."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from database.models import Job, JobCreate, JobLog, JobEvent, OverallStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
repo = JobRepository()
queue = PersistentJobQueue(repo)


class BatchDeleteRequest(BaseModel):
    job_ids: List[int]



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


@router.get("/{job_id}/prompt")
async def get_job_prompt(job_id: int):
    """Get the unique tailored redesign prompt generated for this website."""
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    saved_prompt = (job.design_reference_data or {}).get("lovable_prompt")
    if saved_prompt:
        return {"job_id": job_id, "prompt": saved_prompt}

    from services.lovable.prompt_builder import LovablePromptBuilder
    from services.website_analysis.models import WebsiteAnalysis

    design_data = job.design_reference_data or {}
    analysis_dict = design_data.get("analysis") or {}

    analysis = WebsiteAnalysis(
        url=job.website_url,
        industry=analysis_dict.get("industry") or design_data.get("industry") or "Technology & Business Services",
        category=analysis_dict.get("category") or design_data.get("category") or "Corporate Website",
        target_audience=analysis_dict.get("target_audience") or (job.original_csv_row or {}).get("target_audience") or "B2B",
        business_name=job.business_name or analysis_dict.get("business_name"),
        summary=analysis_dict.get("summary", ""),
        brand_personality=analysis_dict.get("brand_personality", "modern & professional"),
        detected_colors=design_data.get("detected_colors") or analysis_dict.get("detected_colors") or [],
        key_sections=design_data.get("key_sections") or analysis_dict.get("key_sections") or [],
        functional_requirements=analysis_dict.get("functional_requirements") or [],
    )

    ref_dict = design_data.get("selected_reference") or {
        "title": job.design_reference_title or "Modern Aesthetic UI",
        "url": job.design_reference_url or "https://dribbble.com",
        "image_url": job.design_reference_image or "",
        "source": job.design_reference_source or "dribbble",
        "suitability_score": job.design_score or 0.95,
        "rationale": job.design_reason or "",
    }

    notes = (job.input_metadata or {}).get("notes") or (job.original_csv_row or {}).get("notes") or ""
    builder = LovablePromptBuilder()
    prompt = await builder.build_redesign_prompt_async(
        website_url=job.website_url,
        business_name=job.business_name,
        analysis=analysis,
        design_reference=ref_dict,
        additional_instructions=notes,
    )
    return {"job_id": job_id, "prompt": prompt}



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


@router.delete("/all")
@router.post("/delete-all")
def delete_all_jobs():
    """Delete all jobs and associated audit records."""
    deleted_count = repo.delete_all_jobs()
    return {"status": "ok", "deleted_count": deleted_count, "message": f"Deleted {deleted_count} jobs"}


@router.post("/batch-delete")
def batch_delete_jobs(payload: BatchDeleteRequest):
    """Delete multiple selected jobs by integer IDs."""
    deleted_count = repo.delete_jobs(payload.job_ids)
    return {"status": "ok", "deleted_count": deleted_count, "message": f"Deleted {deleted_count} jobs"}


@router.delete("/{job_id}")
def delete_job(job_id: int):
    """Delete a specific job by integer ID."""
    deleted = repo.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "message": f"Job #{job_id} deleted"}
