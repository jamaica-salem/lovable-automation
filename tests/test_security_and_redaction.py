"""Tests for security, token redaction, and safe structured logging."""

import logging
from io import StringIO
from utils.logger import mask_secrets, SecretMaskingFilter, log_external_request, setup_logger


def test_mask_bearer_token():
    raw = "Authorization: Bearer secret_token_abc_12345_xyz"
    masked = mask_secrets(raw)
    assert "secret_token_abc" not in masked
    assert "[REDACTED_TOKEN]" in masked


def test_mask_github_tokens():
    raw_pat = "Connecting with token ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    masked = mask_secrets(raw_pat)
    assert "ghp_1234567890" not in masked
    assert "[REDACTED_GITHUB_PAT]" in masked

    raw_fine = "PAT github_pat_11AAAAAA00000000000000000000000000000000000000000000"
    masked_fine = mask_secrets(raw_fine)
    assert "11AAAAAA000000000000000000000000" not in masked_fine
    assert "[REDACTED_GITHUB_PAT]" in masked_fine


def test_mask_vercel_and_api_keys():
    raw = "Deploying to Vercel with token vercel_abc1234567890xyz and api_key='secret_key_999'"
    masked = mask_secrets(raw)
    assert "vercel_abc1234567890xyz" not in masked
    assert "secret_key_999" not in masked
    assert "[REDACTED" in masked


def test_mask_secrets_in_dict():
    data = {
        "user": "admin",
        "api_key": "super_secret_123",
        "nested": {"access_token": "token_abc_xyz", "safe_field": "hello"},
    }
    masked = mask_secrets(data)
    assert masked["api_key"] == "[REDACTED]"
    assert masked["nested"]["access_token"] == "[REDACTED]"
    assert masked["nested"]["safe_field"] == "hello"


def test_secret_masking_filter_on_logger():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretMaskingFilter())
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    test_log = logging.getLogger("test_masking_logger")
    test_log.setLevel(logging.INFO)
    test_log.addHandler(handler)

    test_log.info("Request failed with header: Bearer sensitive_bearer_999")
    output = stream.getvalue()

    assert "sensitive_bearer_999" not in output
    assert "[REDACTED_TOKEN]" in output


def test_log_external_request_redacts_errors(caplog):
    with caplog.at_level(logging.INFO):
        log_external_request(
            service="lovable",
            operation="create_project",
            job_id=42,
            duration_seconds=0.15,
            success=False,
            error="Invalid token: Bearer my_secret_lovable_key_12345",
        )
    assert "my_secret_lovable_key_12345" not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text
    assert "[ExternalReq] [LOVABLE]" in caplog.text
