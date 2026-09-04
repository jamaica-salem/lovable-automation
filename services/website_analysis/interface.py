"""Website analysis service interface."""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field


class WebsiteAnalysisResult(BaseModel):
    """Extracted structure, industry, and aesthetic analysis of an existing website."""
    url: str
    industry: str
    category: str
    summary: str
    detected_colors: List[str] = Field(default_factory=list)
    key_sections: List[str] = Field(default_factory=list)
    suggested_improvements: List[str] = Field(default_factory=list)


class WebsiteAnalyzerService(ABC):
    """Abstract interface for inspecting and categorizing target websites."""

    @abstractmethod
    async def analyze(self, url: str) -> WebsiteAnalysisResult:
        """Analyze a target website URL and extract industry, style, and structure."""
        pass


class StubWebsiteAnalyzerService(WebsiteAnalyzerService):
    """Stub implementation for foundation chunk."""

    async def analyze(self, url: str) -> WebsiteAnalysisResult:
        # Returns structured architectural baseline without live web scraping
        return WebsiteAnalysisResult(
            url=url,
            industry="Technology & Professional Services",
            category="B2B Corporate Website",
            summary=f"Analysis for {url}: modern SaaS layout with hero, feature grid, and contact CTA.",
            detected_colors=["#0F172A", "#3B82F6", "#F8FAFC"],
            key_sections=["hero", "features", "testimonials", "pricing", "footer"],
            suggested_improvements=[
                "Upgrade typography to modern sans-serif",
                "Add glassmorphism card elevation and subtle micro-interactions",
                "Increase contrast and streamline mobile navigation",
            ],
        )
