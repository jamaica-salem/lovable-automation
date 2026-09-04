"""Tests for worker step execution and decoupled pipeline orchestration."""

from pathlib import Path
import pytest
from database.migrations import init_db
from database.models import DesignStatus, LovableStatus, OverallStatus, VercelStatus
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from workers.design.worker import DesignResearchWorker
from workers.lovable.worker import LovableWorker
from workers.vercel.worker import VercelWorker


@pytest.mark.asyncio
async def test_full_worker_pipeline_step_by_step(tmp_path: Path):
    """Test full sequential and concurrent worker processing across stages."""
    db_file = tmp_path / "worker_pipeline.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repo)

    # Initialize workers
    design_worker = DesignResearchWorker(worker_id="test-d", queue=queue, repository=repo)
    lovable_worker = LovableWorker(worker_id="test-l", queue=queue, repository=repo)
    vercel_worker = VercelWorker(worker_id="test-v", queue=queue, repository=repo)

    # Enqueue two websites
    j1 = queue.enqueue("https://site-alpha.com", csv_row_index=0)
    j2 = queue.enqueue("https://site-beta.com", csv_row_index=1)

    # 1. Step Design Worker for site 1
    did_d1 = await design_worker.step()
    assert did_d1 is True
    site1 = repo.get_job(j1.id)
    assert site1.design_status == DesignStatus.DESIGN_READY
    assert site1.design_duration_seconds is not None

    # 2. Lovable Worker claims site 1 immediately (does NOT wait for site 2)
    did_l1 = await lovable_worker.step()
    assert did_l1 is True
    site1 = repo.get_job(j1.id)
    assert site1.lovable_status == LovableStatus.GITHUB_READY
    assert site1.lovable_published_url is not None
    assert site1.github_repo_url is not None

    # 3. Step Design Worker for site 2
    did_d2 = await design_worker.step()
    assert did_d2 is True
    site2 = repo.get_job(j2.id)
    assert site2.design_status == DesignStatus.DESIGN_READY

    # 4. Lovable Worker can now claim site 2, while Vercel Worker deploys site 1 in parallel!
    did_l2 = await lovable_worker.step()
    assert did_l2 is True
    site2 = repo.get_job(j2.id)
    assert site2.lovable_status == LovableStatus.GITHUB_READY

    # 5. Vercel Worker deploys site 1
    did_v1 = await vercel_worker.step()
    assert did_v1 is True
    site1 = repo.get_job(j1.id)
    assert site1.vercel_status == VercelStatus.DEPLOYED
    assert site1.overall_status == OverallStatus.COMPLETED
    assert site1.total_duration_seconds is not None

    # 6. Vercel Worker deploys site 2
    did_v2 = await vercel_worker.step()
    assert did_v2 is True
    site2 = repo.get_job(j2.id)
    assert site2.vercel_status == VercelStatus.DEPLOYED
    assert site2.overall_status == OverallStatus.COMPLETED
