"""Vercel service package."""
from services.vercel.interface import (
    VercelDeployment,
    VercelService,
    StubVercelService,
)

__all__ = [
    "VercelDeployment",
    "VercelService",
    "StubVercelService",
]
