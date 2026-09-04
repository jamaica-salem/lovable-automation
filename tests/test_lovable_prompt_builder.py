"""Tests for Lovable redesign prompt builder."""

from services.lovable.prompt_builder import LovablePromptBuilder
from services.website_analysis.models import WebsiteAnalysis


def test_prompt_builder_contains_all_required_sections_and_rules():
    builder = LovablePromptBuilder()
    analysis = WebsiteAnalysis(
        url="https://nyc-petcare.com",
        business_name="NYC Petcare",
        industry="Pet & Veterinary Services",
        category="Veterinary Clinic",
        target_audience="B2C",
        brand_personality="compassionate & friendly",
        detected_colors=["#1E3A8A", "#F59E0B", "#10B981"],
        key_sections=["hero", "services", "emergency", "testimonials", "contact", "footer"],
        functional_requirements=["appointment-booking-form", "emergency-call-cta"],
    )

    reference = {
        "title": "Modern Pet Wellness Center & Clinic UI",
        "url": "https://dribbble.com/shots/modern-pet-clinic",
        "image_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c",
        "source": "dribbble",
        "color_palette": ["#0F172A", "#38BDF8", "#F8FAFC"],
        "tags": ["clinic", "pet-care", "clean", "modern", "responsive"],
    }

    prompt = builder.build_redesign_prompt(
        website_url="https://nyc-petcare.com",
        business_name="NYC Petcare",
        analysis=analysis,
        design_reference=reference,
    )

    # 1. Identity & original URL
    assert "NYC Petcare" in prompt
    assert "https://nyc-petcare.com" in prompt
    assert "Veterinary Clinic" in prompt
    assert "B2C" in prompt

    # 2. Brand Preservation Mandate
    assert "PRESERVE ORIGINAL BRAND IDENTITY" in prompt
    assert "PRESERVE ORIGINAL CONTENT" in prompt
    assert "#1E3A8A" in prompt  # Detected brand colors included

    # 3. Reference Details Included
    assert "Modern Pet Wellness Center & Clinic UI" in prompt
    assert "https://dribbble.com/shots/modern-pet-clinic" in prompt

    # 4. Strict Reference Utilization Rule (DO NOT copy reference's identity)
    assert "DO NOT copy the reference website's company name" in prompt
    assert "layout spacing" in prompt

    # 5. Responsive and Accessibility Directives
    assert "Mobile-First" in prompt
    assert "Accessibility (a11y)" in prompt
    assert "No Placeholders" in prompt
