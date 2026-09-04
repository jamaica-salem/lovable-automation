"""Prompt engineering templates for analysis and redesign generation."""

from typing import Any, Dict, List


def generate_redesign_prompt(
    website_url: str,
    industry: str,
    category: str,
    design_reference: Dict[str, Any],
    detected_colors: List[str],
) -> str:
    """Generate structured, production-grade redesign prompt for Lovable."""
    ref_title = design_reference.get("title", "Modern Aesthetic Landing Page")
    ref_palette = design_reference.get("color_palette", ["#0b0f19", "#6366f1", "#f8fafc"])
    ref_tags = ", ".join(design_reference.get("tags", ["modern", "sleek", "responsive"]))

    return f"""Redesign the website for {website_url}.
Target Industry: {industry}
Category: {category}

Design Inspiration & Aesthetic Reference:
- Reference Style: {ref_title}
- Reference Tags: {ref_tags}
- Curated Color Palette: {', '.join(ref_palette)}
- Existing Accent Colors: {', '.join(detected_colors)}

Architectural & UI Directives:
1. Deliver a responsive, state-of-the-art landing page with rich modern aesthetics.
2. Structure key sections: Hero, Problem/Solution, Features Showcase, Social Proof/Testimonials, Interactive Demo/Pricing, and High-Conversion Footer CTA.
3. Use modern typography, subtle glassmorphic surfaces, rich gradients, and micro-interactions.
4. Ensure full accessibility, clean component hierarchy, and fast loading performance.
"""
