"""Targeted search query generation for design references."""

import re
from typing import List
from services.website_analysis.models import WebsiteAnalysis


def generate_search_queries(analysis: WebsiteAnalysis) -> List[str]:
    """Generate 3 to 5 targeted, highly descriptive search queries for design references.
    
    Adheres strictly to the rule: NEVER use generic queries like 'modern website design'.
    Combines industry, website category, layout patterns, brand personality, and audience.
    """
    industry = analysis.industry.lower()
    category = analysis.category.lower()
    tone = analysis.brand_personality.lower().split("&")[0].strip()
    audience = analysis.target_audience.lower()

    # Clean up common connector words
    clean_cat = re.sub(r"\b(website|store|platform|agency)\b", "", category).strip()
    clean_ind = re.sub(r"\b(services|trade|and|&)\b", "", industry).strip()

    primary_keyword = clean_cat or clean_ind or "b2b tech"

    queries: List[str] = []

    # Query 1: Category + Landing Page layout
    queries.append(f"{primary_keyword} landing page ui design".strip())

    # Query 2: Industry + Key section focus (hero / features / portfolio)
    section_focus = "hero clean layout"
    if "pricing" in analysis.key_sections:
        section_focus = "pricing feature grid"
    elif "portfolio" in analysis.key_sections or "work" in analysis.key_sections:
        section_focus = "case study portfolio"
    queries.append(f"{clean_ind} {section_focus}".strip())

    # Query 3: Audience + Tone + Web app / Homepage
    queries.append(f"{audience} {tone} web design interface".strip())

    # Query 4: Aesthetic style + component pattern
    if "minimal" in analysis.content_density:
        queries.append(f"minimalist {primary_keyword} website typography")
    else:
        queries.append(f"modern {primary_keyword} dashboard and web app")

    # Deduplicate and ensure between 3 and 5 queries
    unique_queries = list(dict.fromkeys(queries))
    return unique_queries[:5]
