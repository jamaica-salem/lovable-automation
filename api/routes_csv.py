"""CSV import and export API routes."""

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from csv_pipeline.service import CsvService
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue

router = APIRouter(prefix="/api/csv", tags=["CSV"])
repo = JobRepository()
queue = PersistentJobQueue(repo)
csv_service = CsvService(queue=queue, repository=repo)


@router.post("/import")
async def import_csv(file: UploadFile = File(...)):
    """Import website redesign jobs from an uploaded CSV file."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    with NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        jobs = csv_service.import_csv(tmp_path)
        return {
            "message": f"Successfully imported {len(jobs)} jobs.",
            "imported_count": len(jobs),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV import failed: {str(exc)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.get("/export")
def export_csv():
    """Export updated jobs with deployment URLs and durations to CSV."""
    export_dir = Path("exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / "redesign_jobs_export.csv"

    try:
        csv_service.export_csv(export_path)
        return FileResponse(
            path=str(export_path),
            media_type="text/csv",
            filename="redesign_jobs_export.csv",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CSV export failed: {str(exc)}")
