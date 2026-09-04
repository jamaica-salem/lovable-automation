import asyncio
from pathlib import Path
import pytest

from database.connection import transaction
from database.migrations import init_db
from database.models import (
    DesignStatus,
    JobCreate,
    LovableStatus,
    OverallStatus,
    VercelStatus,
)
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from orchestration.orchestrator import PipelineOrchestrator
from orchestration.recovery import CrashRecoveryManager
from services.dribbble.providers import MockSearchProvider
from services.dribbble.service import DribbbleDesignSearchService
from services.lovable.provider import MockLovableProvider
from services.vercel.provider import MockVercelProvider
from services.website_analysis.models import WebsiteAnalysis


class FastMockAnalyzer:
    async def analyze(self, url: str, business_name: str = None) -> WebsiteAnalysis:
        return WebsiteAnalysis(
            url=url,
            business_name=business_name or "Crash Test Client",
            industry="Technology & SaaS",
            category="Cloud Infrastructure",
            summary="High-performance cloud services and DevOps tooling",
            detected_colors=["#0F172A", "#3B82F6"],
            key_sections=["Hero", "Architecture", "Pricing", "Testimonials"],
        )


@pytest.mark.asyncio
async def test_e2e_crash_recovery_across_all_three_stages(tmp_path: Path):
    """Test crash recovery when all 3 stages have active in-flight jobs.
    
    Setup state at moment of simulated crash:
      - Job #1: in Vercel DEPLOYING (Lovable and GitHub already finished).
      - Job #2: in Lovable GENERATING (Design finished, project_id already provisioned).
      - Job #3: in Design SEARCHING (no reference found yet).
      
    Recovery & Restart verification:
      - Interrupted state detected and recovered.
      - Job #1 does NOT duplicate Lovable generation; deploys cleanly to Vercel.
      - Job #2 preserves existing project_id, does not spawn duplicate Lovable projects.
      - Job #3 resets to DESIGN_QUEUED, completes research, and flows through.
      - All 3 reach COMPLETED status with live URLs.
    """
    db_file = tmp_path / "test_crash_recovery.db"
    init_db(db_file)
    repo = JobRepository(db_path=db_file)
    queue = PersistentJobQueue(repository=repo)

    # 1. Create the 3 jobs
    j1 = repo.create_job(
        JobCreate(
            website_url="https://business-one.com",
            business_name="Business One",
            queue_position=1,
        )
    )
    j2 = repo.create_job(
        JobCreate(
            website_url="https://business-two.com",
            business_name="Business Two",
            queue_position=2,
        )
    )
    j3 = repo.create_job(
        JobCreate(
            website_url="https://business-three.com",
            business_name="Business Three",
            queue_position=3,
        )
    )

    # 2. Simulate Mid-flight Crash State via direct DB state
    with transaction(db_file) as cursor:
        # Job #1: Vercel DEPLOYING, Lovable was already published!
        cursor.execute(
            """
            UPDATE jobs
            SET overall_status = 'PROCESSING',
                design_status = 'DESIGN_READY',
                design_reference_url = 'https://dribbble.com/shots/ref-1',
                design_score = 0.88,
                lovable_status = 'GITHUB_READY',
                lovable_project_id = 'lov_proj_1_existing',
                lovable_published_url = 'https://business-one.lovable.app',
                github_repository = 'org/business-one',
                github_repository_url = 'https://github.com/org/business-one',
                vercel_status = 'DEPLOYING'
            WHERE id = ?
            """,
            (j1.id,),
        )
        # Job #2: Lovable GENERATING (project already assigned in Lovable)
        cursor.execute(
            """
            UPDATE jobs
            SET overall_status = 'PROCESSING',
                design_status = 'DESIGN_READY',
                design_reference_url = 'https://dribbble.com/shots/ref-2',
                design_score = 0.82,
                lovable_status = 'GENERATING',
                lovable_project_id = 'lov_proj_2_preallocated'
            WHERE id = ?
            """,
            (j2.id,),
        )
        # Job #3: Design SEARCHING
        cursor.execute(
            """
            UPDATE jobs
            SET overall_status = 'PROCESSING',
                design_status = 'SEARCHING'
            WHERE id = ?
            """,
            (j3.id,),
        )

    # 3. Application restarts -> CrashRecoveryManager runs
    recovery_mgr = CrashRecoveryManager(repository=repo)
    report = recovery_mgr.recover_interrupted_jobs()

    assert report.stale_jobs_detected == 3
    assert report.design_recovered_count == 1
    assert report.lovable_recovered_count == 1
    assert report.vercel_recovered_count == 1

    # Verify state after recovery
    rec_j1 = repo.get_job_by_id(j1.id)
    rec_j2 = repo.get_job_by_id(j2.id)
    rec_j3 = repo.get_job_by_id(j3.id)

    # Job #1 was GITHUB_READY/DEPLOYING -> reset vercel to VERCEL_QUEUED, Lovable remains GITHUB_READY
    assert rec_j1.lovable_status == LovableStatus.GITHUB_READY
    assert rec_j1.vercel_status == VercelStatus.VERCEL_QUEUED
    assert rec_j1.lovable_published_url == "https://business-one.lovable.app"

    # Job #2 was GENERATING -> reset to WAITING_FOR_DESIGN, preserved project_id
    assert rec_j2.lovable_status == LovableStatus.WAITING_FOR_DESIGN
    assert rec_j2.lovable_project_id == "lov_proj_2_preallocated"
    assert rec_j2.design_status == DesignStatus.DESIGN_READY

    # Job #3 was SEARCHING -> reset to DESIGN_QUEUED
    assert rec_j3.design_status == DesignStatus.DESIGN_QUEUED

    # 4. Now spin up Orchestrator and resume workers
    mock_lovable = MockLovableProvider()
    # Seed the remote Lovable platform with the pre-existing project to simulate realistic remote state
    mock_lovable.projects["lov_proj_2_preallocated"] = {
        "project_id": "lov_proj_2_preallocated",
        "project_name": "Business Two",
        "status": "ready",
        "editor_url": "https://lovable.dev/projects/lov_proj_2_preallocated",
        "preview_url": "https://preview--lov_proj_2_preallocated.lovable.app",
        "prompt": "Redesign Business Two",
        "created_at": "2026-09-04T00:00:00Z",
    }

    mock_vercel = MockVercelProvider()
    mock_search = DribbbleDesignSearchService(provider=MockSearchProvider())
    mock_analyzer = FastMockAnalyzer()

    orchestrator = PipelineOrchestrator(
        repository=repo,
        queue=queue,
        design_concurrency=1,
        vercel_concurrency=1,
        design_buffer_size=3,
        design_analyzer=mock_analyzer,
        dribbble_client=mock_search,
        lovable_provider=mock_lovable,
        vercel_provider=mock_vercel,
    )
    orchestrator._init_workers()

    d_worker = orchestrator.design_workers[0]
    l_worker = orchestrator.lovable_workers[0]
    v_worker = orchestrator.vercel_workers[0]

    # Step workers to completion
    for _ in range(30):
        await d_worker.step()
        await l_worker.step()
        await v_worker.step()

        stats = repo.get_pipeline_stats()
        if stats.completed == 3:
            break

    # 5. Final Validations
    stats = repo.get_pipeline_stats()
    assert stats.completed == 3
    assert stats.failed == 0

    # Ensure no duplicate Lovable projects were created for Job #1 or Job #2
    assert mock_lovable.created_projects_count == 1, (
        f"Expected exactly 1 new project creation (for Job #3), but got {mock_lovable.created_projects_count}"
    )

    final_j1 = repo.get_job_by_id(j1.id)
    final_j2 = repo.get_job_by_id(j2.id)
    final_j3 = repo.get_job_by_id(j3.id)

    # Job #1 should retain its existing lovable published URL and get deployed to vercel
    assert final_j1.overall_status == OverallStatus.COMPLETED
    assert final_j1.lovable_published_url == "https://business-one.lovable.app"
    assert final_j1.vercel_deployment_url is not None

    # Job #2 should complete with both URLs
    assert final_j2.overall_status == OverallStatus.COMPLETED
    assert final_j2.lovable_published_url is not None
    assert final_j2.vercel_deployment_url is not None

    # Job #3 should complete from fresh research through full deployment
    assert final_j3.overall_status == OverallStatus.COMPLETED
    assert final_j3.design_reference_url is not None
    assert final_j3.lovable_published_url is not None
    assert final_j3.vercel_deployment_url is not None
