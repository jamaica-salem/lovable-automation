"""Structured logging utilities with automatic secret masking."""

import json
import logging
import re
import sys
from typing import Any, Dict, Optional, Union
from utils.timestamps import now_iso

# Regex patterns matching sensitive credentials and auth tokens
SECRET_PATTERNS = [
    # Bearer tokens (OAuth, Lovable, Vercel)
    (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # GitHub Personal Access Tokens (Classic and Fine-grained)
    (re.compile(r"ghp_[A-Za-z0-9]{20,}", re.IGNORECASE), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}", re.IGNORECASE), "[REDACTED_GITHUB_OAUTH]"),
    # Vercel tokens
    (re.compile(r"vercel_[A-Za-z0-9_]{16,}", re.IGNORECASE), "[REDACTED_VERCEL_TOKEN]"),
    # Generic key-value secret parameters (URL query, env or log strings)
    (
        re.compile(
            r"((?:api[-_]?key|access[-_]?token|client[-_]?secret|password|auth[-_]?token|token)\s*[:=]\s*)(['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # JSON field secrets
    (
        re.compile(
            r'("(?:api[-_]?key|access[-_]?token|client[-_]?secret|password|auth|authorization)"\s*:\s*")([^"]+)(")',
            re.IGNORECASE,
        ),
        r'\1[REDACTED]\3',
    ),
]


def mask_secrets(text: Any) -> str:
    """Recursively redact secrets and authentication tokens from strings or objects."""
    if text is None:
        return ""
    if isinstance(text, dict):
        sanitized = {}
        for k, v in text.items():
            if any(s in k.lower() for s in ("token", "secret", "password", "key", "auth")):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = mask_secrets(v)
            else:
                sanitized[k] = mask_secrets(str(v))
        return sanitized
    if isinstance(text, list):
        return [mask_secrets(item) for item in text]

    s = str(text)
    for pattern, replacement in SECRET_PATTERNS:
        s = pattern.sub(replacement, s)
    return s


class SecretMaskingFilter(logging.Filter):
    """Logging filter that ensures zero tokens, passwords, or secrets enter log streams."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(mask_secrets(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: mask_secrets(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def setup_logger(name: str = "lovable_automation", level: str = "INFO") -> logging.Logger:
    """Create or configure a structured logger with secret masking."""
    log = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    log.setLevel(numeric_level)

    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretMaskingFilter())
        log.addHandler(handler)

    # Ensure filter is active on all handlers
    for h in log.handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in h.filters):
            h.addFilter(SecretMaskingFilter())

    return log


logger = setup_logger()


def format_log_message(msg: str, job_id: Optional[Union[str, int]] = None, stage: Optional[str] = None) -> str:
    """Format a log message with optional job and stage prefixes and mask secrets."""
    parts = []
    if stage:
        parts.append(f"[{stage}]")
    if job_id:
        parts.append(f"[Job {job_id}]")
    parts.append(mask_secrets(msg))
    return " ".join(parts)


def log_external_request(
    service: str,
    operation: str,
    job_id: Optional[Union[str, int]] = None,
    duration_seconds: float = 0.0,
    success: bool = True,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a structured log entry for an external API or network request.
    
    Fields recorded:
      - service (lovable, vercel, github, dribbble, website)
      - operation (e.g. create_project, wait_for_sync, deploy, fetch_html)
      - job_id
      - timestamp
      - duration_ms
      - success
      - safe_error (masked)
    """
    safe_error = mask_secrets(error) if error else None
    safe_metadata = mask_secrets(metadata) if metadata else None
    duration_ms = round(duration_seconds * 1000.0, 2)

    data = {
        "event": "external_request",
        "service": service,
        "operation": operation,
        "job_id": job_id,
        "timestamp": now_iso(),
        "duration_ms": duration_ms,
        "success": success,
        "error": safe_error,
    }
    if safe_metadata:
        data["metadata"] = safe_metadata

    msg = f"[ExternalReq] [{service.upper()}] {operation} ({duration_ms}ms) - {'SUCCESS' if success else 'FAILED'}"
    if not success and safe_error:
        msg += f" - Error: {safe_error}"

    if success:
        logger.info(format_log_message(msg, job_id=job_id, stage=service))
    else:
        logger.warning(format_log_message(msg, job_id=job_id, stage=service))
