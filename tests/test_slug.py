"""Tests for deterministic slug generation and collision handling."""

from utils.slug import clean_name, extract_domain_name, generate_slug


def test_standard_business_name_slugs():
    """Verify standard business names produce expected modern slugs."""
    assert generate_slug("NYC Petcare") == "nyc-petcare-modern"
    assert generate_slug("Happy Paws Veterinary") == "happy-paws-veterinary-modern"
    assert generate_slug("Austin Dental Clinic") == "austin-dental-clinic-modern"


def test_punctuation_and_special_characters():
    """Verify punctuation, symbols, and accented characters are normalized cleanly."""
    # Accents & symbols
    assert generate_slug("Café & Bistro @ Austin") == "cafe-and-bistro-at-austin-modern"
    # Punctuation & apostrophes
    assert generate_slug("Dr. O'Connor's Diagnostics, Inc.") == "dr-oconnors-diagnostics-inc-modern"
    # Symbols like slashes and brackets
    assert generate_slug("Tech [Global] / Cloud") == "tech-global-cloud-modern"


def test_duplicate_spaces_and_hyphens():
    """Verify duplicate spaces and dashes collapse into single hyphens."""
    assert generate_slug("   Apex    Global   Logistics   ") == "apex-global-logistics-modern"
    assert generate_slug("Prime---Freight--Services") == "prime-freight-services-modern"


def test_extremely_long_names():
    """Verify excessively long names are bounded to safe lengths."""
    long_name = "Super Comprehensive Multi-Disciplinary International Enterprise Consultancy & Solutions"
    slug = generate_slug(long_name, max_name_length=30)
    assert len(slug) <= 40  # 30 + len('-modern')
    assert slug.endswith("-modern")


def test_empty_name_falls_back_to_url():
    """Verify fallback to website domain if business name is empty."""
    assert generate_slug("", website_url="https://acme-logistics.com/about") == "acme-logistics-modern"
    assert generate_slug(None, website_url="https://www.freshmarket.org") == "freshmarket-modern"


def test_collision_handling():
    """Verify duplicate slugs deterministically append suffixes."""
    existing = {"nyc-petcare-modern", "nyc-petcare-modern-2"}
    slug = generate_slug("NYC Petcare", existing_slugs=existing)
    assert slug == "nyc-petcare-modern-3"

    existing.add("nyc-petcare-modern-3")
    slug2 = generate_slug("NYC Petcare", existing_slugs=existing)
    assert slug2 == "nyc-petcare-modern-4"
