import csv
from pathlib import Path
import pytest

from database.migrations import init_db
from database.models import OverallStatus
from database.repository import JobRepository
from csv_pipeline.service import CsvService


def test_e2e_40_jobs_csv_integrity_and_export(tmp_path: Path):
    """Test 40-job CSV lifecycle:
    1. Generate 40-row input CSV with rich custom business metadata.
    2. Import CSV through CsvService into persistent database.
    3. Verify all 40 rows preserved in exact queue order with zero loss.
    4. Simulate completion with Lovable and Vercel production URLs.
    5. Export to output CSV via atomic writer.
    6. Validate exported CSV:
       - Exactly 40 data rows.
       - Original order matches input order 1..40.
       - All original metadata columns preserved intact.
       - Output URLs correctly populated (lovable_url, vercel_url).
       - Zero duplicate rows, zero corrupted rows.
    """
    db_file = tmp_path / "test_csv_integrity.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    csv_service = CsvService(repository=repo)

    input_csv_path = tmp_path / "input_40_clients.csv"
    output_csv_path = tmp_path / "output_40_clients.csv"

    # 1. Generate 40-row CSV with diverse client metadata
    num_rows = 40
    input_rows = []
    fieldnames = [
        "website_url",
        "business_name",
        "industry",
        "city",
        "contact_email",
        "tier",
        "special_instructions",
    ]

    for i in range(1, num_rows + 1):
        row = {
            "website_url": f"https://client-{i:02d}.com",
            "business_name": f"Client Venture {i:02d} LLC",
            "industry": "Healthcare" if i % 2 == 0 else "Fintech",
            "city": f"Metropolis {i}",
            "contact_email": f"partner_{i:02d}@client-{i:02d}.com",
            "tier": "Enterprise" if i % 5 == 0 else "Growth",
            "special_instructions": f"Ensure dark mode and booking widget for client {i:02d}",
        }
        input_rows.append(row)

    with open(input_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(input_rows)

    # 2. Ingest CSV
    import_result = csv_service.import_csv(input_csv_path)
    assert len(import_result) == num_rows

    # 3. Verify Database State
    jobs = repo.list_jobs(limit=100)
    assert len(jobs) == num_rows

    # Ensure queue positions 1..40 strictly sequential
    for i, job in enumerate(jobs, start=1):
        assert job.queue_position == i
        assert job.website_url == input_rows[i - 1]["website_url"]
        assert job.business_name == input_rows[i - 1]["business_name"]
        assert job.original_csv_row.get("tier") == input_rows[i - 1]["tier"]
        assert job.original_csv_row.get("city") == input_rows[i - 1]["city"]

    # 4. Simulate Complete Pipeline Processing
    from database.connection import transaction
    for i, job in enumerate(jobs, start=1):
        slug = f"client-{i:02d}-modern"
        lov_url = f"https://{slug}.lovable.app"
        ver_url = f"https://{slug}.vercel.app"

        with transaction(db_file) as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET overall_status = 'COMPLETED',
                    design_status = 'DESIGN_READY',
                    design_reference_url = ?,
                    design_score = 0.85,
                    lovable_status = 'PUBLISHED',
                    lovable_project_id = ?,
                    lovable_published_url = ?,
                    github_status = 'SYNCED',
                    github_repository_url = ?,
                    vercel_status = 'DEPLOYED',
                    vercel_deployment_url = ?,
                    project_slug = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    f"https://dribbble.com/shots/ref-{i}",
                    f"proj_lov_{i:02d}",
                    lov_url,
                    f"https://github.com/org/{slug}",
                    ver_url,
                    slug,
                    job.id,
                ),
            )

    # 5. Export to CSV
    exported_file = csv_service.export_csv(output_csv_path)
    assert exported_file.exists()
    assert exported_file == output_csv_path

    # 6. Read and Thoroughly Validate Exported CSV
    with open(exported_file, mode="r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    # Assert exact row count
    assert len(reader) == num_rows, f"Expected {num_rows} exported rows, got {len(reader)}"

    seen_urls = set()
    seen_positions = set()

    for idx, row in enumerate(reader, start=1):
        expected_input = input_rows[idx - 1]

        # Order check
        assert int(row["queue_position"]) == idx
        assert row["queue_position"] not in seen_positions
        seen_positions.add(row["queue_position"])

        # No duplicate website URLs
        assert row["website_url"] == expected_input["website_url"]
        assert row["website_url"] not in seen_urls
        seen_urls.add(row["website_url"])

        # Metadata preservation check
        assert row["business_name"] == expected_input["business_name"]
        assert row["industry"] == expected_input["industry"]
        assert row["city"] == expected_input["city"]
        assert row["contact_email"] == expected_input["contact_email"]
        assert row["tier"] == expected_input["tier"]
        assert row["special_instructions"] == expected_input["special_instructions"]

        # Production URLs and status check
        expected_slug = f"client-{idx:02d}-modern"
        assert row["status"] == OverallStatus.COMPLETED.value
        assert row["lovable_url"] == f"https://{expected_slug}.lovable.app"
        assert row["vercel_url"] == f"https://{expected_slug}.vercel.app"
        assert row["vercel_deployment_url"] == f"https://{expected_slug}.vercel.app"
        assert row["project_slug"] == expected_slug
        assert row["error_message"] == ""
