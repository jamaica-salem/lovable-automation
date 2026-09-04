"""Timestamp and duration calculation utilities."""

from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """Return current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """Return current UTC datetime in ISO-8601 string format."""
    return now_utc().isoformat()


def parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 string to timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def calculate_duration_seconds(start_ts: Optional[str], end_ts: Optional[str]) -> Optional[float]:
    """Calculate elapsed duration in seconds between two ISO-8601 timestamp strings."""
    start_dt = parse_iso(start_ts)
    end_dt = parse_iso(end_ts)
    if not start_dt or not end_dt:
        return None
    diff = (end_dt - start_dt).total_seconds()
    return max(0.0, round(diff, 2))
