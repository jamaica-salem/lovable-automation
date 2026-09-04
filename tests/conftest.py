"""Pytest configuration ensuring automated tests run on an isolated database."""

import os
import pytest
from pathlib import Path
from app.config import settings
from database.migrations import init_db


@pytest.fixture(autouse=True, scope="session")
def isolate_test_database(tmp_path_factory):
    """Ensure automated tests run against an isolated temporary database, protecting jobs.db."""
    test_db_dir = tmp_path_factory.mktemp("db")
    test_db_path = test_db_dir / "test_session_jobs.db"
    settings.database_path = test_db_path
    os.environ["DATABASE_PATH"] = str(test_db_path)
    init_db(test_db_path)
    yield
