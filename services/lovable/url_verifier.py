"""HTTP-based verification for published Lovable deployment URLs."""

import time
from typing import Optional
import httpx

from services.lovable.models import UrlVerificationResult
from utils.logger import logger
from utils.timestamps import now_iso


class LovableUrlVerifier:
    """Verifies that published Lovable applications are live and returning healthy HTTP responses."""

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    async def verify(self, url: str) -> UrlVerificationResult:
        """Perform live HTTP check against target URL and record latency and status code."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Lovable-Automation-Verifier/1.0"},
            ) as client:
                response = await client.get(clean_url)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                is_ok = 200 <= response.status_code < 400

                return UrlVerificationResult(
                    url=clean_url,
                    status_code=response.status_code,
                    response_time_ms=elapsed_ms,
                    is_reachable=is_ok,
                    verified_at=now_iso(),
                    error=None if is_ok else f"HTTP status {response.status_code}",
                )

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(f"URL verification failed for {clean_url}: {exc}")
            return UrlVerificationResult(
                url=clean_url,
                status_code=0,
                response_time_ms=elapsed_ms,
                is_reachable=False,
                verified_at=now_iso(),
                error=str(exc),
            )
