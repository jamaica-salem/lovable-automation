"""Database schema migrations and initialization."""

from pathlib import Path
from typing import Union
from database.connection import get_connection
from utils.logger import logger

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT UNIQUE NOT NULL,
    csv_row_index INTEGER NOT NULL,
    website_url TEXT NOT NULL,
    input_metadata TEXT NOT NULL DEFAULT '{}',

    -- Status dimensions
    overall_status TEXT NOT NULL DEFAULT 'PENDING',
    design_status TEXT NOT NULL DEFAULT 'DESIGN_QUEUED',
    lovable_status TEXT NOT NULL DEFAULT 'WAITING_FOR_DESIGN',
    vercel_status TEXT NOT NULL DEFAULT 'VERCEL_QUEUED',

    -- Outputs and artifacts
    design_reference_data TEXT,
    lovable_project_id TEXT,
    lovable_published_url TEXT,
    github_repo_url TEXT,
    vercel_deployment_url TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    design_started_at TEXT,
    design_completed_at TEXT,
    lovable_started_at TEXT,
    lovable_completed_at TEXT,
    lovable_published_at TEXT,
    github_synced_at TEXT,
    vercel_started_at TEXT,
    vercel_completed_at TEXT,
    verification_started_at TEXT,
    verification_completed_at TEXT,
    job_completed_at TEXT,

    -- Calculated duration metrics in seconds
    design_duration_seconds REAL,
    lovable_duration_seconds REAL,
    lovable_publish_duration_seconds REAL,
    github_sync_duration_seconds REAL,
    vercel_duration_seconds REAL,
    verification_duration_seconds REAL,
    total_duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    job_uid TEXT NOT NULL,
    stage TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_overall_status ON jobs(overall_status);
CREATE INDEX IF NOT EXISTS idx_jobs_design_status ON jobs(design_status);
CREATE INDEX IF NOT EXISTS idx_jobs_lovable_status ON jobs(lovable_status);
CREATE INDEX IF NOT EXISTS idx_jobs_vercel_status ON jobs(vercel_status);
CREATE INDEX IF NOT EXISTS idx_jobs_csv_row_index ON jobs(csv_row_index);
CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
"""


def init_db(db_path: Union[str, Path] = None) -> None:
    """Initialize database tables and indexes."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        logger.info("Database schema initialized successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
