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


EXCLUDED_AUTHORS: Set[str] = {
    "jamaica salem",
    "jamaicasalem",
    "jamaica-salem",
}

EXCLUDED_SHOT_IDS: Set[str] = {
    "24009083",
}

EXCLUDED_TITLES: Set[str] = {
    "news website design",
}

# Non-web graphic assets that must NEVER be used as website redesign references
EXCLUDED_GRAPHIC_KEYWORDS: Set[str] = {
    "illustration",
    "illustrations",
    "3d illustration",
    "icon",
    "icons",
    "icon set",
    "logo",
    "logo design",
    "mascot",
    "sticker",
    "stickers",
    "character",
    "poster",
    "packaging",
    "vector art",
    "clipart",
    "badge",
}

# Explicit web design markers required for modern layout references
REQUIRED_WEB_KEYWORDS: Set[str] = {
    "website",
    "web design",
    "web",
    "landing page",
    "landing",
    "ui",
    "ui/ux",
    "portal",
    "dashboard",
    "web app",
    "platform",
    "homepage",
    "desktop",
}


def is_personal_or_excluded_reference(candidate: DesignCandidate) -> bool:
    """Strictly filter out authenticated user's personal uploads or blacklisted portfolio shots."""
    author = (candidate.author or "").strip().lower()
    if author in EXCLUDED_AUTHORS:
        return True

    title = (candidate.title or "").strip().lower()
    if title in EXCLUDED_TITLES:
        return True

    url = (candidate.url or "").strip().lower()
    for shot_id in EXCLUDED_SHOT_IDS:
        if shot_id in url or shot_id in candidate.id:
            return True

    if "jamaica-salem" in url or "jamaicasalem" in url:
        return True

    return False


def is_graphic_asset_not_web_design(candidate: DesignCandidate) -> bool:
    """Check if a candidate represents non-web graphics (illustration, icons, stickers, logo)."""
    text_corpus = f"{candidate.title} {' '.join(candidate.tags)}".lower()
    has_graphic = any(g in text_corpus for g in EXCLUDED_GRAPHIC_KEYWORDS)
    has_web = any(w in text_corpus for w in REQUIRED_WEB_KEYWORDS)
    return has_graphic and not has_web


def deduplicate_candidates(candidates: List[DesignCandidate]) -> List[DesignCandidate]:
    """Remove duplicate design candidates based on URL and image URL, excluding any user personal uploads."""
    seen_urls: Set[str] = set()
    seen_images: Set[str] = set()
    unique: List[DesignCandidate] = []

    for candidate in candidates:
        if is_personal_or_excluded_reference(candidate):
            continue

        norm_url = candidate.url.strip().rstrip("/").lower()
        norm_img = candidate.image_url.strip().lower()

        if norm_url in seen_urls or (norm_img and norm_img in seen_images):
            continue

        seen_urls.add(norm_url)
        if norm_img:
            seen_images.add(norm_img)
        unique.append(candidate)

    return unique
