"""Unit and integration tests for job deletion functionality."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from database.migrations import init_db
from database.models import JobCreate
from database.repository import JobRepository
from app.main import app


@pytest.fixture
def test_repo(tmp_path: Path):
    db_file = tmp_path / "test_deletion.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    return repo


def test_delete_single_job(test_repo):
    job = test_repo.create_job(JobCreate(website_url="https://site1.example.com", csv_row_index=0))
    assert test_repo.get_job(job.id) is not None

    deleted = test_repo.delete_job(job.id)
    assert deleted is True
    assert test_repo.get_job(job.id) is None

    # Deleting again returns False
    assert test_repo.delete_job(job.id) is False


def test_delete_multiple_jobs(test_repo):
    j1 = test_repo.create_job(JobCreate(website_url="https://site1.example.com", csv_row_index=0))
    j2 = test_repo.create_job(JobCreate(website_url="https://site2.example.com", csv_row_index=1))
    j3 = test_repo.create_job(JobCreate(website_url="https://site3.example.com", csv_row_index=2))

    deleted_count = test_repo.delete_jobs([j1.id, j3.id, 999999])
    assert deleted_count == 2
    assert test_repo.get_job(j1.id) is None
    assert test_repo.get_job(j3.id) is None
    assert test_repo.get_job(j2.id) is not None


def test_delete_all_jobs(test_repo):
    test_repo.create_job(JobCreate(website_url="https://site1.example.com", csv_row_index=0))
    test_repo.create_job(JobCreate(website_url="https://site2.example.com", csv_row_index=1))

    assert len(test_repo.list_jobs()) == 2
    count = test_repo.delete_all_jobs()
    assert count == 2
    assert len(test_repo.list_jobs()) == 0


def test_api_job_deletion_routes():
    client = TestClient(app)

    # 1. Create a job via API
    res = client.post("/api/jobs", json={"website_url": "https://delete-me.example.com", "csv_row_index": 99})
    assert res.status_code == 200
    job = res.json()
    job_id = job["id"]

    # 2. Delete single job
    del_res = client.delete(f"/api/jobs/{job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "ok"

    # 3. Verify it's gone
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.delete(f"/api/jobs/{job_id}").status_code == 404

    # 4. Create multiple jobs and test batch delete
    j1 = client.post("/api/jobs", json={"website_url": "https://del1.example.com", "csv_row_index": 100}).json()
    j2 = client.post("/api/jobs", json={"website_url": "https://del2.example.com", "csv_row_index": 101}).json()

    batch_res = client.post("/api/jobs/batch-delete", json={"job_ids": [j1["id"], j2["id"]]})
    assert batch_res.status_code == 200
    assert batch_res.json()["deleted_count"] >= 2

    # 5. Test delete-all
    client.post("/api/jobs", json={"website_url": "https://del-all.example.com", "csv_row_index": 102})
    del_all_res = client.post("/api/jobs/delete-all")
    assert del_all_res.status_code == 200
    assert del_all_res.json()["status"] == "ok"
