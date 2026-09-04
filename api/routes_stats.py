"""Pipeline statistics and system health API routes."""

from fastapi import APIRouter
from database.models import PipelineStats
from database.repository import JobRepository

router = APIRouter(prefix="/api/stats", tags=["Stats"])
repo = JobRepository()


@router.get("", response_model=PipelineStats)
def get_stats():
    """Retrieve aggregate counts for all discrete pipeline stages."""
    return repo.get_pipeline_stats()
