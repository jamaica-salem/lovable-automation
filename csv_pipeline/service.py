"""CSV import and export service matching Chunk 2 specifications."""

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple, Union
from database.models import Job
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from utils.logger import logger

URL_CANDIDATE_COLUMNS = ["website_url", "url", "website", "domain", "link", "site", "target_url"]
BUSINESS_CANDIDATE_COLUMNS = ["business_name", "company_name", "business", "company", "name", "client"]
LIVE_EXPORT_PATH = Path("exports/redesign_jobs_live.csv")


class CsvService:
    """Service handling non-destructive CSV import with duplicate prevention and export."""

    def __init__(self, queue: Optional[PersistentJobQueue] = None, repository: Optional[JobRepository] = None):
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)

    @staticmethod
    def _detect_column(fieldnames: List[str], candidates: List[str]) -> Optional[str]:
        """Detect column matching candidate list."""
        for field in fieldnames:
            if field.strip().lower() in candidates:
                return field
        return None

    def import_csv(
        self,
        file_path: Union[str, Path],
        allow_duplicates: bool = False,
    ) -> List[Job]:
        """Import website redesign jobs from a CSV file.
        
        - Preserves strict CSV row order.
        - Assigns 1-based queue_position.
        - Preserves all original columns in original_csv_row.
        - Prevents duplicate jobs on re-import unless allow_duplicates=True.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        created_jobs: List[Job] = []
        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError(f"Empty CSV or missing headers: {path}")

            url_col = self._detect_column(reader.fieldnames, URL_CANDIDATE_COLUMNS) or reader.fieldnames[0]
            name_col = self._detect_column(reader.fieldnames, BUSINESS_CANDIDATE_COLUMNS)

            logger.info(f"Importing CSV {path}. Detected URL column: '{url_col}', Name column: '{name_col}'")

            current_max_pos = self.repo.count_jobs()

            for row_index, row in enumerate(reader):
                raw_url = (row.get(url_col) or "").strip()
                if not raw_url:
                    continue

                if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                    website_url = f"https://{raw_url}"
                else:
                    website_url = raw_url

                # Check duplicate prevention
                if not allow_duplicates:
                    existing = self.repo.get_job_by_url(website_url)
                    if existing:
                        logger.info(f"Skipping duplicate website {website_url} (existing job ID: {existing.id})")
                        created_jobs.append(existing)
                        continue

                b_name = (row.get(name_col) or "").strip() if name_col else None
                queue_pos = current_max_pos + len(created_jobs) + 1

                # Safe copy of original row
                original_row = {k: v for k, v in row.items()}

                job = self.queue.enqueue(
                    website_url=website_url,
                    queue_position=queue_pos,
                    business_name=b_name,
                    original_csv_row=original_row,
                    csv_row_index=row_index,
                    allow_duplicates=True,  # Checked above
                )
                created_jobs.append(job)

        logger.info(f"Import finished for {path}: processed {len(created_jobs)} jobs.")
        return created_jobs

    def export_csv(self, output_path: Union[str, Path]) -> Path:
        """Export jobs to CSV preserving original columns and appending results:
        website_url,lovable_url,vercel_url,status plus original columns.
        """
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        jobs = self.repo.list_jobs(limit=100000, offset=0)
        jobs.sort(key=lambda j: j.queue_position)

        # 1. Discover all original keys across jobs
        original_keys: List[str] = []
        for j in jobs:
            row_dict = j.original_csv_row or j.input_metadata or {}
            for k in row_dict.keys():
                if k not in original_keys and k not in ("website_url", "lovable_url", "vercel_url", "status"):
                    original_keys.append(k)

        # 2. Base output columns specified by Chunk 2:
        # website_url, lovable_url, vercel_url, status + original columns
        primary_columns = ["website_url", "lovable_url", "vercel_url", "status"]
        
        # Additional operational columns (optional metadata appended after)
        operational_columns = ["vercel_deployment_url", "overall_status", "queue_position", "project_slug", "error_message", "total_duration_seconds"]

        fieldnames = list(primary_columns)
        for k in original_keys:
            if k not in fieldnames:
                fieldnames.append(k)
        for k in operational_columns:
            if k not in fieldnames:
                fieldnames.append(k)

        # Atomic write to temporary file
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=out_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()

            for j in jobs:
                row_data: Dict[str, Any] = dict(j.original_csv_row or j.input_metadata or {})
                v_url = j.vercel_url or j.vercel_deployment_url or ""
                row_data.update(
                    {
                        "website_url": j.website_url,
                        "lovable_url": j.lovable_published_url or "",
                        "vercel_url": v_url,
                        "vercel_deployment_url": v_url,
                        "status": j.overall_status.value,
                        "overall_status": j.overall_status.value,
                        "queue_position": j.queue_position,
                        "project_slug": j.project_slug or "",
                        "error_message": j.error_message or "",
                    }
                )
                writer.writerow({k: row_data.get(k, "") for k in fieldnames})

        os.replace(temp_path, out_path)
        logger.info(f"Successfully exported {len(jobs)} jobs to {out_path}")
        return out_path

    def auto_export(self, target_path: Optional[Union[str, Path]] = None) -> Path:
        """Automatically export live jobs status to CSV on completion or status change.

        Uses atomic file replacement to guarantee zero file corruption on crash.
        """
        path = Path(target_path) if target_path else Path(LIVE_EXPORT_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return self.export_csv(path)


# Alias for pipeline callers
CsvPipelineService = CsvService

