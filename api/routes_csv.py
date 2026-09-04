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


from datetime import datetime

@router.get("/export")
def export_csv():
    """Export updated jobs with deployment URLs and durations to CSV with timestamp."""
    export_dir = Path("exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    timestamped_filename = f"redesign_jobs_{timestamp_str}.csv"
    export_path = export_dir / timestamped_filename

    try:
        csv_service.export_csv(export_path)
        # Also copy to static redesign_jobs_export.csv for backward compatibility
        shutil.copy2(export_path, export_dir / "redesign_jobs_export.csv")
        return FileResponse(
            path=str(export_path),
            media_type="text/csv",
            filename=timestamped_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{timestamped_filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CSV export failed: {str(exc)}")


@router.get("/exports")
def list_exports():
    """List all available CSV export files with metadata and timestamps."""
    export_dir = Path("exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    
    files = []
    # Find all .csv files sorted by latest modified date
    for p in sorted(export_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = p.stat()
        mtime_dt = datetime.fromtimestamp(stat.st_mtime)
        mtime_str = mtime_dt.strftime("%Y-%m-%d %H:%M:%S")
        size_kb = round(stat.st_size / 1024.0, 2)
        size_display = f"{size_kb} KB" if stat.st_size >= 1024 else f"{stat.st_size} B"
        
        files.append({
            "filename": p.name,
            "size_bytes": stat.st_size,
            "size_formatted": size_display,
            "modified_at": mtime_str,
            "download_url": f"/api/csv/download/{p.name}",
        })
    
    return {"exports": files, "count": len(files)}


@router.get("/download/{filename}")
def download_export(filename: str):
    """Download a specific exported CSV file by name."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    export_path = Path("exports") / filename
    if not export_path.exists() or not export_path.is_file():
        raise HTTPException(status_code=404, detail="Exported CSV file not found")
    
    return FileResponse(
        path=str(export_path),
        media_type="text/csv",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )

