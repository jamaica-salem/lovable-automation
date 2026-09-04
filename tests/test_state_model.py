"""Tests for the job state model and enums."""

from database.models import DesignStatus, LovableStatus, OverallStatus, VercelStatus
from utils.timestamps import calculate_duration_seconds, now_iso, parse_iso


def test_state_enums_completeness():
    """Verify all required statuses exist and are distinct (not collapsed)."""
    # Design states
    expected_design = {
        "DESIGN_QUEUED",
        "ANALYZING",
        "SEARCHING",
        "EVALUATING",
        "DESIGN_READY",
        "DESIGN_FAILED",
        "DESIGN_NEEDS_REVIEW",
    }
    actual_design = {s.value for s in DesignStatus}
    assert expected_design == actual_design

    # Lovable states
    expected_lovable = {
        "WAITING_FOR_DESIGN",
        "PREPARING",
        "SUBMITTING",
        "GENERATING",
        "VERIFYING",
        "PUBLISHING",
        "PUBLISHED",
        "GITHUB_SYNCING",
        "GITHUB_READY",
        "FAILED",
    }
    actual_lovable = {s.value for s in LovableStatus}
    assert expected_lovable == actual_lovable

    # Vercel states
    expected_vercel = {
        "VERCEL_QUEUED",
        "DEPLOYING",
        "VERIFYING",
        "DEPLOYED",
        "FAILED",
    }
    actual_vercel = {s.value for s in VercelStatus}
    assert expected_vercel == actual_vercel

    # Overall states
    expected_overall = {
        "PENDING",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "PAUSED",
    }
    actual_overall = {s.value for s in OverallStatus}
    assert expected_overall == actual_overall


def test_timestamp_durations():
    """Test duration calculation utility."""
    start = "2026-09-04T10:00:00+00:00"
    end = "2026-09-04T10:05:30+00:00"
    duration = calculate_duration_seconds(start, end)
    assert duration == 330.0

    # Invalid timestamp handling
    assert calculate_duration_seconds(None, end) is None
    assert calculate_duration_seconds("invalid", end) is None
