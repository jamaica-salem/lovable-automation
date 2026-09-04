"""Command Line Interface for Lovable Automation Platform."""

import argparse
import sys
from pathlib import Path
import uvicorn

from app.config import settings
from csv_pipeline.service import CsvService
from database.migrations import init_db
from database.repository import JobRepository
from job_queue.persistent_queue import PersistentJobQueue


def cmd_init_db(args):
    """Initialize the database schema."""
    init_db(settings.database_path)
    print(f"Database initialized at: {settings.database_path}")


def cmd_run(args):
    """Run the FastAPI application with Uvicorn."""
    host = args.host or settings.host
    port = args.port or settings.port
    print(f"Starting {settings.app_name} on http://{host}:{port}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_import_csv(args):
    """Import jobs from a CSV file."""
    csv_path = Path(args.file)
    if not csv_path.exists():
        print(f"Error: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    repo = JobRepository(settings.database_path)
    init_db(settings.database_path)
    queue = PersistentJobQueue(repo)
    service = CsvService(queue=queue, repository=repo)

    jobs = service.import_csv(csv_path)
    print(f"Successfully enqueued {len(jobs)} jobs from {csv_path}")


def cmd_export_csv(args):
    """Export jobs to a CSV file."""
    out_path = Path(args.output)
    repo = JobRepository(settings.database_path)
    init_db(settings.database_path)
    queue = PersistentJobQueue(repo)
    service = CsvService(queue=queue, repository=repo)

    result_path = service.export_csv(out_path)
    print(f"Exported jobs to: {result_path}")


def cmd_status(args):
    """Display current pipeline status and counts."""
    repo = JobRepository(settings.database_path)
    init_db(settings.database_path)
    stats = repo.get_pipeline_stats()

    print("\n--- Lovable Automation Pipeline Status ---")
    print(f"Total Jobs:           {stats.total_jobs}")
    print(f"Pending:              {stats.pending}")
    print(f"Design Research:      {stats.design_research}")
    print(f"Waiting for Lovable:  {stats.waiting_for_lovable}")
    print(f"Lovable Processing:   {stats.lovable_processing} (Concurrency Mutex: 1)")
    print(f"Vercel Deployment:    {stats.vercel_deployment}")
    print(f"Completed:            {stats.completed}")
    print(f"Failed:               {stats.failed}")
    print("-------------------------------------------\n")


def main():
    parser = argparse.ArgumentParser(
        prog="lovable-automation",
        description="Lovable Automation Platform CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize SQLite database schema")

    # run
    run_parser = subparsers.add_parser("run", help="Start web app and background workers")
    run_parser.add_argument("--host", default=None, help="Host to bind to (default: 127.0.0.1)")
    run_parser.add_argument("--port", type=int, default=None, help="Port to bind to (default: 8080)")
    run_parser.add_argument("--reload", action="store_true", help="Enable hot reload")

    # import-csv
    import_parser = subparsers.add_parser("import-csv", help="Import a CSV of websites")
    import_parser.add_argument("file", help="Path to CSV file")

    # export-csv
    export_parser = subparsers.add_parser("export-csv", help="Export jobs to CSV")
    export_parser.add_argument("--output", default="redesign_jobs_export.csv", help="Output file path")

    # status
    subparsers.add_parser("status", help="Print pipeline status metrics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init-db": cmd_init_db,
        "run": cmd_run,
        "import-csv": cmd_import_csv,
        "export-csv": cmd_export_csv,
        "status": cmd_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
