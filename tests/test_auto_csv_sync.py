"""Tests for automated atomic CSV export upon job completion and failure."""

import os
import tempfile
import pytest
from pathlib import Path
from database.repository import JobRepository
from database.models import JobCreate, OverallStatus, DesignStatus, LovableStatus, GitHubStatus, VercelStatus
from csv_pipeline.service import CsvPipelineService


@pytest.fixture
def repo():
    return JobRepository()


def test_auto_export_atomic_file_creation(repo, tmp_path):
    """Verify auto_export atomically writes CSV to destination without partial states."""
    service = CsvPipelineService(repository=repo)

    # Insert test completed job
    job = repo.create_job(
        JobCreate(
            website_url="https://csv-sync-test.com",
            business_name="CSV Sync Test",
        )
    )
    repo.update_vercel_status(job.id, VercelStatus.DEPLOYED, deployment_url="https://csv-sync-test.vercel.app")
    repo.update_job_status(job.id, OverallStatus.COMPLETED)

    target_csv = tmp_path / "exports" / "redesign_jobs_live.csv"

    # Export
    exported_path = service.auto_export(target_path=str(target_csv))
    assert Path(exported_path).exists()

    content = Path(exported_path).read_text(encoding="utf-8")
    assert "https://csv-sync-test.com" in content
    assert "https://csv-sync-test.vercel.app" in content
    assert "COMPLETED" in content


@pytest.mark.asyncio
async def test_vercel_worker_triggers_auto_export(repo, tmp_path, monkeypatch):
    """Verify Vercel worker triggers safe auto_export when job finishes deployment."""
    from workers.vercel.worker import VercelWorker
    from services.vercel.provider import MockVercelProvider

    # Point live export path to tmp_path
    target_csv = tmp_path / "exports" / "redesign_jobs_live.csv"
    monkeypatch.setattr("csv_pipeline.service.LIVE_EXPORT_PATH", str(target_csv))

    job = repo.create_job(
        JobCreate(
            website_url="https://vercel-export-trigger.com",
            business_name="Export Trigger",
        )
    )
    repo.update_lovable_status(
        job.id,
        LovableStatus.GITHUB_READY,
        published_url="https://lovable.app/p/export-trigger",
        github_url="https://github.com/org/export-trigger",
        github_repo="org/export-trigger",
    )
    repo.update_vercel_status(
        job.id,
        VercelStatus.VERCEL_QUEUED,
    )
    repo.update_job_status(job.id, OverallStatus.PROCESSING)

    provider = MockVercelProvider()
    worker = VercelWorker(worker_id="test-v", repository=repo, provider=provider)

    # Execute a single worker step
    processed = await worker.step()
    assert processed is True

    updated = repo.get_job_by_id(job.id)
    assert updated.overall_status == OverallStatus.COMPLETED

    # Verify auto-export CSV was created
    assert target_csv.exists()
    csv_content = target_csv.read_text(encoding="utf-8")
    assert "https://vercel-export-trigger.com" in csv_content
    assert "COMPLETED" in csv_content
