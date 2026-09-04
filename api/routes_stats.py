"""Pipeline statistics, metrics, and system health API routes."""

from fastapi import APIRouter
from database.models import PipelineStats
from database.repository import JobRepository
from orchestration.metrics import PipelineMetricsCollector, PipelineMetrics

router = APIRouter(prefix="/api/stats", tags=["Stats"])
repo = JobRepository()
metrics_collector = PipelineMetricsCollector(repo)


@router.get("", response_model=PipelineStats)
def get_stats():
    """Retrieve aggregate counts for all discrete pipeline stages."""
    return repo.get_pipeline_stats()


@router.get("/pipeline", response_model=PipelineMetrics)
def get_pipeline_metrics():
    """Retrieve detailed stage durations, throughput, queue depths, and KPIs."""
    return metrics_collector.calculate_metrics()


@router.get("/health")
def get_health_status():
    """Retrieve pipeline health summary and queue depths."""
    metrics = metrics_collector.calculate_metrics()
    return {
        "status": "HEALTHY",
        "design_queue_depth": metrics.design_queue_depth,
        "vercel_queue_depth": metrics.vercel_queue_depth,
        "completed_sites_per_hour": metrics.completed_sites_per_hour,
        "lovable_utilization": metrics.lovable_utilization,
        "failure_rate": metrics.failure_rate,
        "retry_rate": metrics.retry_rate,
    }
