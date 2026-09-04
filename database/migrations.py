"""Database schema migrations and initialization for Chunk 2."""

from pathlib import Path
from typing import Union
from database.connection import get_connection
from utils.logger import logger

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT UNIQUE NOT NULL,
    queue_position INTEGER NOT NULL DEFAULT 1,
    website_url TEXT NOT NULL,
    business_name TEXT,
    project_slug TEXT,
    original_csv_row TEXT NOT NULL DEFAULT '{}',
    csv_row_index INTEGER DEFAULT 0,
    input_metadata TEXT NOT NULL DEFAULT '{}',

    -- Status dimensions
    overall_status TEXT NOT NULL DEFAULT 'PENDING',
    design_status TEXT NOT NULL DEFAULT 'DESIGN_QUEUED',
    lovable_status TEXT NOT NULL DEFAULT 'WAITING_FOR_DESIGN',
    github_status TEXT NOT NULL DEFAULT 'GITHUB_PENDING',
    vercel_status TEXT NOT NULL DEFAULT 'VERCEL_QUEUED',

    -- Design Research fields
    design_reference_url TEXT,
    design_reference_image TEXT,
    design_reference_title TEXT,
    design_reference_source TEXT,
    design_score REAL,
    design_reason TEXT,
    design_error TEXT,
    design_reference_data TEXT,

    -- Lovable fields
    lovable_project_id TEXT,
    lovable_editor_url TEXT,
    lovable_preview_url TEXT,
    lovable_published_url TEXT,

    -- GitHub fields
    github_repository TEXT,
    github_repository_url TEXT,
    github_repo_url TEXT,
    github_commit_sha TEXT,

    -- Vercel fields
    vercel_project_id TEXT,
    vercel_deployment_id TEXT,
    vercel_url TEXT,
    vercel_deployment_url TEXT,

    -- Error tracking and retries
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    design_started_at TEXT,
    design_completed_at TEXT,
    lovable_started_at TEXT,
    lovable_completed_at TEXT,
    published_at TEXT,
    lovable_published_at TEXT,
    github_started_at TEXT,
    github_completed_at TEXT,
    github_synced_at TEXT,
    vercel_started_at TEXT,
    vercel_completed_at TEXT,
    completed_at TEXT,
    job_completed_at TEXT,

    -- Durations (seconds)
    design_duration_seconds REAL,
    lovable_duration_seconds REAL,
    lovable_publish_duration_seconds REAL,
    github_sync_duration_seconds REAL,
    vercel_duration_seconds REAL,
    verification_duration_seconds REAL,
    total_duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    message TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
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
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_jobs_queue_position ON jobs(queue_position);
CREATE INDEX IF NOT EXISTS idx_jobs_website_url ON jobs(website_url);
CREATE INDEX IF NOT EXISTS idx_jobs_project_slug ON jobs(project_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_overall_status ON jobs(overall_status);
CREATE INDEX IF NOT EXISTS idx_jobs_design_status ON jobs(design_status);
CREATE INDEX IF NOT EXISTS idx_jobs_lovable_status ON jobs(lovable_status);
CREATE INDEX IF NOT EXISTS idx_jobs_vercel_status ON jobs(vercel_status);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_event_type ON job_events(event_type);
CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
"""

ADDITIONAL_COLUMNS = [
    ("queue_position", "INTEGER NOT NULL DEFAULT 1"),
    ("business_name", "TEXT"),
    ("project_slug", "TEXT"),
    ("original_csv_row", "TEXT NOT NULL DEFAULT '{}'"),
    ("github_status", "TEXT NOT NULL DEFAULT 'GITHUB_PENDING'"),
    ("design_reference_url", "TEXT"),
    ("design_reference_image", "TEXT"),
    ("design_reference_title", "TEXT"),
    ("design_reference_source", "TEXT"),
    ("design_score", "REAL"),
    ("design_reason", "TEXT"),
    ("design_error", "TEXT"),
    ("lovable_editor_url", "TEXT"),
    ("lovable_preview_url", "TEXT"),
    ("github_repository", "TEXT"),
    ("github_repo_url", "TEXT"),
    ("github_commit_sha", "TEXT"),
    ("vercel_project_id", "TEXT"),
    ("vercel_deployment_id", "TEXT"),
    ("vercel_url", "TEXT"),
    ("published_at", "TEXT"),
    ("github_started_at", "TEXT"),
    ("github_completed_at", "TEXT"),
    ("completed_at", "TEXT"),
]


def init_db(db_path: Union[str, Path] = None) -> None:
    """Initialize database tables and upgrade existing tables if needed."""
    conn = get_connection(db_path)
    try:
        # 1. Ensure tables exist
        conn.executescript(TABLES_SQL)

        # 2. Non-destructive upgrade for any columns missing from existing tables
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(jobs);")
        existing_cols = {row["name"] for row in cursor.fetchall()}

        for col_name, col_type in ADDITIONAL_COLUMNS:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type};")
                    logger.info(f"Added column {col_name} to jobs table.")
                except Exception as exc:
                    logger.debug(f"Column {col_name} already exists or error: {exc}")

        # 3. Create performance indexes once all columns exist
        conn.executescript(INDEXES_SQL)

        logger.info("Database schema initialized and verified successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
