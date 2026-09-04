"""SQLite database connection manager with WAL mode and transaction support."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union
from app.config import settings
from utils.logger import logger


def get_connection(db_path: Union[str, Path] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with WAL mode and row factory."""
    target_path = Path(db_path) if db_path else settings.database_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=settings.sqlite_busy_timeout_ms / 1000.0,
        isolation_level=None,  # Autocommit mode; we manage transactions explicitly
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Performance and concurrency pragmas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms};")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn


@contextmanager
def get_db_cursor(db_path: Union[str, Path] = None) -> Generator[sqlite3.Cursor, None, None]:
    """Context manager for executing database commands with automatic cleanup."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.close()


@contextmanager
def transaction(db_path: Union[str, Path] = None) -> Generator[sqlite3.Cursor, None, None]:
    """Context manager for atomic database transactions with BEGIN IMMEDIATE."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE;")
        yield cursor
        cursor.execute("COMMIT;")
    except Exception as exc:
        cursor.execute("ROLLBACK;")
        logger.error(f"Database transaction failed and was rolled back: {exc}")
        raise
    finally:
        cursor.close()
        conn.close()
