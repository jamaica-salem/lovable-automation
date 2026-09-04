"""Website analysis models and schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WebsiteAnalysis(BaseModel):
    """Structured architectural and aesthetic analysis of a target website."""

    url: str
    business_name: Optional[str] = None

    # 15 Specific Evaluation Dimensions
    industry: str = "Technology & Business Services"
    category: str = "Corporate Website"
    target_audience: str = "B2B"  # B2B, B2C, Enterprise, Consumer
    content_density: str = "moderate"  # minimal, moderate, dense
    detected_colors: List[str] = Field(default_factory=list)
    typography_style: str = "modern-sans-serif"
    key_sections: List[str] = Field(default_factory=list)
    imagery_style: str = "photography"  # photography, illustrations, 3D, icon-heavy
    brand_personality: str = "professional"  # playful, corporate, luxury, technical, friendly
    mobile_responsive: bool = True
    visual_strengths: List[str] = Field(default_factory=list)
    visual_weaknesses: List[str] = Field(default_factory=list)
    redesign_opportunities: List[str] = Field(default_factory=list)
    functional_requirements: List[str] = Field(default_factory=list)
    content_structure: Dict[str, Any] = Field(default_factory=dict)

    # High-level summary & operational flags
    summary: str = ""
    suggested_improvements: List[str] = Field(default_factory=list)
    offline_fallback: bool = False
    raw_title: Optional[str] = None
    meta_description: Optional[str] = None


# Backward-compatibility alias for Chunk 1 / 2 code
WebsiteAnalysisResult = WebsiteAnalysis
