"""Tests for CSV import and export preserving order and metadata."""

import csv
from pathlib import Path
import pytest
from csv_pipeline.service import CsvService
from database.migrations import init_db
from database.models import OverallStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue


@pytest.fixture
def csv_env(tmp_path: Path):
    db_file = tmp_path / "csv_test.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repo)
    service = CsvService(queue=queue, repository=repo)
    return service, repo, tmp_path


def test_csv_import_and_export(csv_env):
    """Test importing CSV with extra custom columns and exporting without corruption."""
    service, repo, tmp_dir = csv_env

    # 1. Create source CSV
    src_csv = tmp_dir / "input.csv"
    src_data = [
        {"website_url": "https://alpha.example.com", "client": "Alpha Corp", "priority": "high"},
        {"website_url": "https://beta.example.com", "client": "Beta Inc", "priority": "medium"},
        {"website_url": "https://gamma.example.com", "client": "Gamma LLC", "priority": "low"},
    ]
    with open(src_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["website_url", "client", "priority"])
        writer.writeheader()
        writer.writerows(src_data)

    # 2. Import CSV
    jobs = service.import_csv(src_csv)
    assert len(jobs) == 3
    assert jobs[0].website_url == "https://alpha.example.com"
    assert jobs[0].csv_row_index == 0
    assert jobs[0].input_metadata["client"] == "Alpha Corp"
    assert jobs[1].csv_row_index == 1
    assert jobs[2].csv_row_index == 2

    # 3. Simulate completion of job 0
    repo.update_vercel_status(
        jobs[0].id,
        status="DEPLOYED",
        deployment_url="https://alpha-redesign.vercel.app",
    )

    # 4. Export CSV
    out_csv = tmp_dir / "output.csv"
    service.export_csv(out_csv)
    assert out_csv.exists()

    with open(out_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        exported = list(reader)

    assert len(exported) == 3
    # Check that original columns are preserved
    assert exported[0]["client"] == "Alpha Corp"
    assert exported[0]["priority"] == "high"
    assert exported[0]["vercel_deployment_url"] == "https://alpha-redesign.vercel.app"
    assert exported[0]["overall_status"] == "COMPLETED"

    assert exported[1]["client"] == "Beta Inc"
    assert exported[1]["priority"] == "medium"
    assert exported[1]["overall_status"] == "PENDING"
