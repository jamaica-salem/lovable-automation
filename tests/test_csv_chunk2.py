"""Tests for Chunk 2 CSV Import, Duplicate Prevention, and CSV Export."""

import csv
from pathlib import Path
import pytest
from csv_pipeline.service import CsvService
from database.migrations import init_db
from database.models import DesignStatus, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue


@pytest.fixture
def chunk2_csv_env(tmp_path: Path):
    db_file = tmp_path / "chunk2_csv.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repo)
    service = CsvService(queue=queue, repository=repo)
    return service, repo, queue, tmp_path


def test_csv_import_and_duplicate_prevention(chunk2_csv_env):
    """Verify CSV import assigns queue_position, initial statuses, preserves original columns,
    and prevents duplicates on re-import unless explicitly requested.
    """
    service, repo, queue, tmp_dir = chunk2_csv_env

    # 1. Prepare sample CSV
    csv_file = tmp_dir / "clients.csv"
    rows = [
        {"website_url": "https://alpha.com", "business_name": "Alpha Corp", "region": "North America"},
        {"website_url": "https://beta.com", "business_name": "Beta Health", "region": "Europe"},
        {"website_url": "https://gamma.com", "business_name": "Gamma Tech", "region": "Asia-Pacific"},
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["website_url", "business_name", "region"])
        writer.writeheader()
        writer.writerows(rows)

    # 2. First import
    imported_1 = service.import_csv(csv_file)
    assert len(imported_1) == 3
    assert imported_1[0].queue_position == 1
    assert imported_1[0].website_url == "https://alpha.com"
    assert imported_1[0].business_name == "Alpha Corp"
    assert imported_1[0].project_slug == "alpha-corp-modern"
    assert imported_1[0].original_csv_row["region"] == "North America"
    assert imported_1[0].design_status == DesignStatus.DESIGN_QUEUED
    assert imported_1[0].lovable_status == LovableStatus.WAITING_FOR_DESIGN
    assert imported_1[0].vercel_status == VercelStatus.VERCEL_QUEUED
    assert imported_1[0].overall_status == OverallStatus.PENDING

    assert imported_1[1].queue_position == 2
    assert imported_1[2].queue_position == 3
    assert repo.count_jobs() == 3

    # 3. Re-import the exact same CSV (Default: allow_duplicates=False)
    imported_2 = service.import_csv(csv_file, allow_duplicates=False)
    assert len(imported_2) == 3
    # Total jobs in database must STILL be 3 (no duplicates created)
    assert repo.count_jobs() == 3
    assert imported_2[0].id == imported_1[0].id


def test_csv_export_format_and_column_preservation(chunk2_csv_env):
    """Verify CSV export contains:
    website_url,lovable_url,vercel_url,status
    plus the original columns, without destroying original data.
    """
    service, repo, queue, tmp_dir = chunk2_csv_env

    csv_file = tmp_dir / "sites.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["website_url", "business_name", "tier", "contact_email"])
        writer.writeheader()
        writer.writerow({
            "website_url": "https://example.com",
            "business_name": "Example Co",
            "tier": "enterprise",
            "contact_email": "admin@example.com",
        })

    jobs = service.import_csv(csv_file)
    job = jobs[0]

    # Simulate full completion of redesign
    repo.update_design_status(job.id, DesignStatus.DESIGN_READY, design_data={"selected_reference": {"title": "Ref"}})
    repo.update_lovable_status(job.id, LovableStatus.PUBLISHED, published_url="https://example-modern.lovable.app")
    repo.update_vercel_status(job.id, VercelStatus.DEPLOYED, deployment_url="https://example-modern.vercel.app")

    out_file = tmp_dir / "exported_results.csv"
    service.export_csv(out_file)
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)

    # Verify primary headers are present
    assert "website_url" in headers
    assert "lovable_url" in headers
    assert "vercel_url" in headers
    assert "status" in headers

    # Verify original custom columns are preserved
    assert "business_name" in headers
    assert "tier" in headers
    assert "contact_email" in headers

    # Verify content
    row = rows[0]
    assert row["website_url"] == "https://example.com"
    assert row["lovable_url"] == "https://example-modern.lovable.app"
    assert row["vercel_url"] == "https://example-modern.vercel.app"
    assert row["status"] == "COMPLETED"
    assert row["tier"] == "enterprise"
    assert row["contact_email"] == "admin@example.com"
