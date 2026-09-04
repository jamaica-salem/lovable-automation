"""Design search and reference selection service interface."""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field


class DesignReference(BaseModel):
    """Modern design reference representation."""
    reference_id: str
    title: str
    source: str = "dribbble"
    url: str
    image_url: str
    author: str
    tags: List[str] = Field(default_factory=list)
    color_palette: List[str] = Field(default_factory=list)
    suitability_score: float = 0.95
    rationale: str = ""


class DesignSearchService(ABC):
    """Interface for searching and evaluating modern design references."""

    @abstractmethod
    async def search_references(self, industry: str, category: str) -> List[DesignReference]:
        """Search references matching industry and category."""
        pass

    @abstractmethod
    async def evaluate_and_select_best(
        self, references: List[DesignReference], industry: str
    ) -> DesignReference:
        """Score candidate references and select the best fit."""
        pass


class StubDesignSearchService(DesignSearchService):
    """Stub implementation for foundation chunk."""

    async def search_references(self, industry: str, category: str) -> List[DesignReference]:
        return [
            DesignReference(
                reference_id="ref_modern_saas_01",
                title=f"Modern Dark Mode Dashboard & Landing for {industry}",
                source="dribbble",
                url="https://dribbble.com/shots/example-modern-saas",
                image_url="https://images.unsplash.com/photo-1460925895917-afdab827c52f",
                author="Studio Apex",
                tags=["dark-mode", "glassmorphism", "b2b", "sleek", "modern-typography"],
                color_palette=["#0b0f19", "#6366f1", "#10b981", "#f8fafc"],
                suitability_score=0.96,
                rationale=f"High alignment with {category} aesthetic, sleek dark theme with glowing accents.",
            )
        ]

    async def evaluate_and_select_best(
        self, references: List[DesignReference], industry: str
    ) -> DesignReference:
        if not references:
            raise ValueError("No references to evaluate")
        return max(references, key=lambda r: r.suitability_score)
