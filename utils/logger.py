"""Structured logging utilities."""

import logging
import sys
from typing import Optional


def setup_logger(name: str = "lovable_automation", level: str = "INFO") -> logging.Logger:
    """Create or configure a structured logger."""
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()


def format_log_message(msg: str, job_id: Optional[str] = None, stage: Optional[str] = None) -> str:
    """Format a message with optional job and stage prefixes."""
    parts = []
    if stage:
        parts.append(f"[{stage}]")
    if job_id:
        parts.append(f"[Job {job_id}]")
    parts.append(msg)
    return " ".join(parts)
