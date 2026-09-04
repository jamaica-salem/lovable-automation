"""Tests for targeted design query generation."""

from services.dribbble.query_generator import generate_search_queries
from services.website_analysis.models import WebsiteAnalysis


def test_targeted_queries_avoid_generic_phrases():
    analysis = WebsiteAnalysis(
        url="https://fintech-saas.com",
        industry="Software & Technology",
        category="SaaS Platform",
        target_audience="B2B",
        brand_personality="innovative & technical",
        content_density="moderate",
        key_sections=["hero", "features", "pricing", "contact"],
    )

    queries = generate_search_queries(analysis)

    assert 3 <= len(queries) <= 5
    for q in queries:
        # Strictly verify no generic "modern website design" query
        assert q.lower() != "modern website design"
        assert len(q.split()) >= 3  # Sufficiently descriptive

    # Must contain relevant category or industry concepts
    joined = " ".join(queries).lower()
    assert "saas" in joined or "software" in joined or "tech" in joined
    assert "b2b" in joined or "innovative" in joined


def test_ecommerce_query_generation():
    analysis = WebsiteAnalysis(
        url="https://artisan-goods.com",
        industry="E-Commerce & Retail",
        category="E-Commerce Store",
        target_audience="B2C",
        brand_personality="vibrant & transactional",
        content_density="minimal",
        key_sections=["hero", "products", "cart", "footer"],
    )

    queries = generate_search_queries(analysis)
    assert 3 <= len(queries) <= 5
    joined = " ".join(queries).lower()
    assert "ecommerce" in joined or "minimalist" in joined or "landing page" in joined
