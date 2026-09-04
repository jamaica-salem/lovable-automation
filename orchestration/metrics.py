"""Pipeline metrics models and collector calculating stage durations and KPIs."""

import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from database.repository import JobRepository
from database.connection import get_db_cursor
from utils.logger import logger


class PipelineMetrics(BaseModel):
    """Real-time performance metrics and aggregate KPIs across the redesign pipeline."""

    # Stage Durations (averages in seconds for completed jobs)
    avg_design_duration_seconds: Optional[float] = None
    avg_lovable_generation_duration_seconds: Optional[float] = None
    avg_lovable_publish_duration_seconds: Optional[float] = None
    avg_github_sync_duration_seconds: Optional[float] = None
    avg_vercel_deployment_duration_seconds: Optional[float] = None
    avg_verification_duration_seconds: Optional[float] = None
    avg_total_duration_seconds: Optional[float] = None

    # Pipeline KPIs
    average_time_per_site: Optional[float] = None
    completed_sites_per_hour: float = 0.0
    design_queue_depth: int = 0
    lovable_utilization: float = 0.0  # 0.0 to 100.0%
    vercel_queue_depth: int = 0
    failure_rate: float = 0.0         # 0.0 to 100.0%
    retry_rate: float = 0.0           # 0.0 to 100.0%

    # Counters
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    in_progress_jobs: int = 0
    retried_jobs: int = 0
    uptime_seconds: float = 0.0


class PipelineMetricsCollector:
    """Collects and computes aggregate metrics from the repository and worker runtime."""

    def __init__(self, repository: Optional[JobRepository] = None):
        self.repo = repository or JobRepository()
        self._start_time: float = time.monotonic()
        self._lovable_busy_start: Optional[float] = None
        self._total_lovable_busy_seconds: float = 0.0

    def mark_lovable_busy(self) -> None:
        """Mark Lovable worker as actively generating."""
        if self._lovable_busy_start is None:
            self._lovable_busy_start = time.monotonic()

    def mark_lovable_idle(self) -> None:
        """Mark Lovable worker as idle/waiting."""
        if self._lovable_busy_start is not None:
            elapsed = time.monotonic() - self._lovable_busy_start
            self._total_lovable_busy_seconds += max(0.0, elapsed)
            self._lovable_busy_start = None

    def get_uptime_seconds(self) -> float:
        """Get elapsed collector uptime in seconds."""
        return max(0.001, time.monotonic() - self._start_time)

    def calculate_metrics(self) -> PipelineMetrics:
        """Calculate and return full pipeline metrics and KPIs."""
        uptime = self.get_uptime_seconds()

        # Update current Lovable busy slice if actively running
        current_lovable_busy = self._total_lovable_busy_seconds
        if self._lovable_busy_start is not None:
            current_lovable_busy += max(0.0, time.monotonic() - self._lovable_busy_start)

        with get_db_cursor(self.repo.db_path) as cursor:
            # 1. Overall counts
            cursor.execute("SELECT COUNT(*) FROM jobs")
            total_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE overall_status = 'COMPLETED'")
            completed_jobs = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs 
                WHERE overall_status = 'FAILED'
                   OR design_status = 'DESIGN_FAILED'
                   OR lovable_status = 'FAILED'
                   OR vercel_status = 'FAILED'
                """
            )
            failed_jobs = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs 
                WHERE overall_status = 'PROCESSING'
                   OR design_status IN ('ANALYZING', 'SEARCHING', 'EVALUATING')
                   OR lovable_status IN ('PREPARING', 'SUBMITTING', 'GENERATING', 'VERIFYING', 'PUBLISHING', 'GITHUB_SYNCING')
                   OR vercel_status IN ('DEPLOYING', 'VERIFYING')
                """
            )
            in_progress_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE retry_count > 0")
            retried_jobs = cursor.fetchone()[0]

            # 2. Queue Depths (active non-failed, non-completed jobs)
            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs 
                WHERE design_status = 'DESIGN_QUEUED'
                  AND overall_status NOT IN ('FAILED', 'COMPLETED', 'PAUSED')
                """
            )
            design_queue_depth = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM jobs 
                WHERE vercel_status = 'VERCEL_QUEUED' 
                  AND lovable_status = 'GITHUB_READY'
                  AND overall_status NOT IN ('FAILED', 'COMPLETED', 'PAUSED')
                """
            )
            vercel_queue_depth = cursor.fetchone()[0]

            # 3. Stage Durations for completed jobs
            cursor.execute(
                """
                SELECT 
                    AVG(design_duration_seconds),
                    AVG(lovable_duration_seconds),
                    AVG(lovable_publish_duration_seconds),
                    AVG(github_sync_duration_seconds),
                    AVG(vercel_duration_seconds),
                    AVG(verification_duration_seconds),
                    AVG(total_duration_seconds)
                FROM jobs
                WHERE overall_status = 'COMPLETED'
                """
            )
            row = cursor.fetchone()
            avg_design = round(row[0], 2) if row and row[0] is not None else None
            avg_lovable_gen = round(row[1], 2) if row and row[1] is not None else None
            avg_lovable_pub = round(row[2], 2) if row and row[2] is not None else None
            avg_gh_sync = round(row[3], 2) if row and row[3] is not None else None
            avg_vercel = round(row[4], 2) if row and row[4] is not None else None
            avg_verify = round(row[5], 2) if row and row[5] is not None else None
            avg_total = round(row[6], 2) if row and row[6] is not None else None

        # 4. KPI Calculations
        failure_rate = round((failed_jobs / total_jobs * 100.0), 2) if total_jobs > 0 else 0.0
        retry_rate = round((retried_jobs / total_jobs * 100.0), 2) if total_jobs > 0 else 0.0

        # Lovable Utilization: % of time busy vs total runtime
        if current_lovable_busy > 0 and uptime > 0:
            lovable_util = min(100.0, (current_lovable_busy / uptime) * 100.0)
        else:
            is_busy = self.repo.is_lovable_worker_busy()
            lovable_util = 100.0 if is_busy else 0.0
        lovable_utilization = round(lovable_util, 2)

        # Completed sites per hour
        if uptime > 10.0 and completed_jobs > 0:
            sites_per_hour = (completed_jobs / uptime) * 3600.0
        elif avg_total and avg_total > 0:
            sites_per_hour = (3600.0 / avg_total)
        else:
            sites_per_hour = 0.0
        completed_sites_per_hour = round(sites_per_hour, 2)

        return PipelineMetrics(
            avg_design_duration_seconds=avg_design,
            avg_lovable_generation_duration_seconds=avg_lovable_gen,
            avg_lovable_publish_duration_seconds=avg_lovable_pub,
            avg_github_sync_duration_seconds=avg_gh_sync,
            avg_vercel_deployment_duration_seconds=avg_vercel,
            avg_verification_duration_seconds=avg_verify,
            avg_total_duration_seconds=avg_total,
            average_time_per_site=avg_total,
            completed_sites_per_hour=completed_sites_per_hour,
            design_queue_depth=design_queue_depth,
            lovable_utilization=lovable_utilization,
            vercel_queue_depth=vercel_queue_depth,
            failure_rate=failure_rate,
            retry_rate=retry_rate,
            total_jobs=total_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            in_progress_jobs=in_progress_jobs,
            retried_jobs=retried_jobs,
            uptime_seconds=round(uptime, 2),
        )
