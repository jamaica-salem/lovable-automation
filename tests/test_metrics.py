"""Unit and integration tests for PipelineMetricsCollector."""

from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import JobCreate, DesignStatus, LovableStatus, VercelStatus
from database.repository import JobRepository
from orchestration.metrics import PipelineMetricsCollector


@pytest.fixture
def test_repo(tmp_path: Path):
    db_file = tmp_path / "test_metrics.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    return repo


def test_metrics_empty_pipeline(test_repo):
    collector = PipelineMetricsCollector(repository=test_repo)
    metrics = collector.calculate_metrics()

    assert metrics.total_jobs == 0
    assert metrics.completed_jobs == 0
    assert metrics.failure_rate == 0.0
    assert metrics.retry_rate == 0.0
    assert metrics.design_queue_depth == 0
    assert metrics.vercel_queue_depth == 0
    assert metrics.average_time_per_site is None


def test_metrics_populated_pipeline_durations_and_kpis(test_repo):
    repo = test_repo
    collector = PipelineMetricsCollector(repository=repo)

    # Job 1: Completed cleanly in 300s total duration
    j1 = repo.create_job(JobCreate(website_url="https://site-alpha.com", queue_position=1))
    repo.update_design_status(j1.id, DesignStatus.DESIGN_READY, design_data={"industry": "Tech"})
    repo.update_lovable_status(
        j1.id,
        LovableStatus.GITHUB_READY,
        published_url="https://site-alpha.lovable.app",
        github_url="https://github.com/org/site-alpha",
    )
    repo.update_vercel_status(
        j1.id,
        VercelStatus.DEPLOYED,
        deployment_url="https://site-alpha.vercel.app",
        project_id="prj_alpha",
    )

    # Manually populate duration fields on j1 to test exact duration math
    from database.connection import transaction
    with transaction(repo.db_path) as cursor:
        cursor.execute(
            """
            UPDATE jobs
            SET design_duration_seconds = 40.0,
                lovable_duration_seconds = 180.0,
                lovable_publish_duration_seconds = 30.0,
                github_sync_duration_seconds = 10.0,
                vercel_duration_seconds = 35.0,
                verification_duration_seconds = 5.0,
                total_duration_seconds = 300.0,
                retry_count = 1
            WHERE id = ?
            """,
            (j1.id,),
        )

    # Job 2: Failed job
    j2 = repo.create_job(JobCreate(website_url="https://site-beta.com", queue_position=2))
    repo.mark_job_failed(j2.id, error_message="Build failure", stage="Lovable")

    # Job 3: Queued in design
    j3 = repo.create_job(JobCreate(website_url="https://site-gamma.com", queue_position=3))

    # Job 4: In Vercel queue
    j4 = repo.create_job(JobCreate(website_url="https://site-delta.com", queue_position=4))
    repo.update_design_status(j4.id, DesignStatus.DESIGN_READY)
    repo.update_lovable_status(
        j4.id,
        LovableStatus.GITHUB_READY,
        published_url="https://site-delta.lovable.app",
        github_url="https://github.com/org/site-delta",
    )

    metrics = collector.calculate_metrics()

    assert metrics.total_jobs == 4
    assert metrics.completed_jobs == 1
    assert metrics.failed_jobs == 1
    assert metrics.design_queue_depth == 1  # j3
    assert metrics.vercel_queue_depth == 1  # j4
    assert metrics.failure_rate == 25.0     # 1 / 4
    assert metrics.retry_rate == 25.0       # 1 / 4 (j1 had retry_count=1)

    # Duration averages
    assert metrics.avg_design_duration_seconds == 40.0
    assert metrics.avg_lovable_generation_duration_seconds == 180.0
    assert metrics.avg_lovable_publish_duration_seconds == 30.0
    assert metrics.avg_github_sync_duration_seconds == 10.0
    assert metrics.avg_vercel_deployment_duration_seconds == 35.0
    assert metrics.avg_verification_duration_seconds == 5.0
    assert metrics.avg_total_duration_seconds == 300.0
    assert metrics.average_time_per_site == 300.0
    assert metrics.completed_sites_per_hour == 12.0  # 3600 / 300 = 12.0 sites/hr
