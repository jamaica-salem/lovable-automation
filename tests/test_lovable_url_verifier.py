"""Tests for live Lovable URL verifier."""

import pytest
from services.lovable.url_verifier import LovableUrlVerifier


@pytest.mark.asyncio
async def test_url_verifier_measures_latency_and_handles_unreachable():
    verifier = LovableUrlVerifier(timeout_seconds=0.5)

    # Test unreachable non-existent domain
    result = await verifier.verify("https://non-existent-deployment-xyz-123.lovable.app")
    assert result.is_reachable is False
    assert result.status_code in (0, 404)
    assert result.error is not None
    assert result.response_time_ms >= 0.0
    assert result.verified_at != ""
