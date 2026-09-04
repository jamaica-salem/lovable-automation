"""CSV import and export service."""

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Union
from database.models import Job
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue
from utils.logger import logger

URL_CANDIDATE_COLUMNS = ["website_url", "url", "website", "domain", "link", "site", "target_url"]


class CsvService:
    """Service handling non-destructive CSV import and export."""

    def __init__(self, queue: Optional[PersistentJobQueue] = None, repository: Optional[JobRepository] = None):
        self.repo = repository or JobRepository()
        self.queue = queue or PersistentJobQueue(self.repo)

    @staticmethod
    def _detect_url_column(fieldnames: List[str]) -> str:
        """Detect the URL column name from candidate headers or default to the first column."""
        for field in fieldnames:
            if field.strip().lower() in URL_CANDIDATE_COLUMNS:
                return field
        return fieldnames[0] if fieldnames else "website_url"

    def import_csv(self, file_path: Union[str, Path]) -> List[Job]:
        """Import jobs from CSV, preserving original row order and all extra columns."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        created_jobs: List[Job] = []
        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError(f"Empty CSV or missing headers: {path}")

            url_col = self._detect_url_column(reader.fieldnames)
            logger.info(f"Importing CSV {path}. Detected website URL column: '{url_col}'")

            for row_index, row in enumerate(reader):
                raw_url = (row.get(url_col) or "").strip()
                if not raw_url:
                    continue

                # Ensure URL has scheme
                if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                    website_url = f"https://{raw_url}"
                else:
                    website_url = raw_url

                # Save all original columns in input_metadata
                input_metadata = {k: v for k, v in row.items()}
                job = self.queue.enqueue(
                    website_url=website_url,
                    csv_row_index=row_index,
                    input_metadata=input_metadata,
                )
                created_jobs.append(job)

        logger.info(f"Successfully imported {len(created_jobs)} jobs from {path}")
        return created_jobs

    def export_csv(self, output_path: Union[str, Path]) -> Path:
        """Export all jobs to CSV in original row order, appending results safely."""
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        jobs = self.repo.list_jobs(limit=100000, offset=0)
        jobs.sort(key=lambda j: j.csv_row_index)

        # Collect original input keys to preserve schema
        original_keys: List[str] = []
        for j in jobs:
            for k in (j.input_metadata or {}).keys():
                if k not in original_keys:
                    original_keys.append(k)

        # Additional result columns
        result_columns = [
            "website_url",
            "overall_status",
            "design_status",
            "lovable_status",
            "vercel_status",
            "lovable_published_url",
            "github_repo_url",
            "vercel_deployment_url",
            "total_duration_seconds",
            "error_message",
        ]

        fieldnames = list(original_keys)
        for col in result_columns:
            if col not in fieldnames:
                fieldnames.append(col)

        # Atomic write to temporary file before replacing target
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
                row_data: Dict[str, Any] = dict(j.input_metadata or {})
                row_data.update(
                    {
                        "website_url": j.website_url,
                        "overall_status": j.overall_status.value,
                        "design_status": j.design_status.value,
                        "lovable_status": j.lovable_status.value,
                        "vercel_status": j.vercel_status.value,
                        "lovable_published_url": j.lovable_published_url or "",
                        "github_repo_url": j.github_repo_url or "",
                        "vercel_deployment_url": j.vercel_deployment_url or "",
                        "total_duration_seconds": j.total_duration_seconds or "",
                        "error_message": j.error_message or "",
                    }
                )
                writer.writerow({k: row_data.get(k, "") for k in fieldnames})

        os.replace(temp_path, out_path)
        logger.info(f"Successfully exported {len(jobs)} jobs to {out_path}")
        return out_path
