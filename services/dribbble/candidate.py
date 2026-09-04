"""Design reference candidate models and deduplication."""

from typing import List, Set
from pydantic import BaseModel, Field


class DesignCandidate(BaseModel):
    """Candidate modern design reference evaluated for redesign suitability."""

    id: str
    title: str
    url: str
    image_url: str
    author: str
    source: str = "dribbble"  # "dribbble", "web", or "mock"
    tags: List[str] = Field(default_factory=list)
    color_palette: List[str] = Field(default_factory=list)

    # 5 Weighted Criteria Scores (0.0 to 1.0)
    industry_score: float = 0.0
    style_score: float = 0.0
    modernity_score: float = 0.0
    layout_score: float = 0.0
    brand_compatibility_score: float = 0.0

    # Composite weighted score
    overall_score: float = 0.0
    evaluation_notes: str = ""

    # Legacy compatibility fields
    @property
    def suitability_score(self) -> float:
        return self.overall_score

    @property
    def rationale(self) -> str:
        return self.evaluation_notes


def deduplicate_candidates(candidates: List[DesignCandidate]) -> List[DesignCandidate]:
    """Remove duplicate design candidates based on URL and image URL."""
    seen_urls: Set[str] = set()
    seen_images: Set[str] = set()
    unique: List[DesignCandidate] = []

    for candidate in candidates:
        norm_url = candidate.url.strip().rstrip("/").lower()
        norm_img = candidate.image_url.strip().lower()

        if norm_url in seen_urls or (norm_img and norm_img in seen_images):
            continue

        seen_urls.add(norm_url)
        if norm_img:
            seen_images.add(norm_img)
        unique.append(candidate)

    return unique
