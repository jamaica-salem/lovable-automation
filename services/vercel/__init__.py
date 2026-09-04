"""Vercel integration package."""

from services.vercel.interface import (
    StubVercelService,
    VercelDeployment as BaseVercelDeployment,
    VercelService,
)
from services.vercel.models import (
    VercelDeployment,
    VercelProject,
    VercelVerificationResult,
)
from services.vercel.provider import (
    MockVercelProvider,
    OfficialApiVercelProvider,
    VercelProvider,
)

__all__ = [
    "VercelProject",
    "VercelDeployment",
    "VercelVerificationResult",
    "VercelProvider",
    "OfficialApiVercelProvider",
    "MockVercelProvider",
    "VercelService",
    "StubVercelService",
    "BaseVercelDeployment",
]
