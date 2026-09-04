"""API routes package."""
from api.routes_csv import router as csv_router
from api.routes_jobs import router as jobs_router
from api.routes_stats import router as stats_router

__all__ = ["jobs_router", "csv_router", "stats_router"]
