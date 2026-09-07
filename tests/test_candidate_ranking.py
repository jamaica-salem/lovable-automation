"""Tests for candidate ranking formula, weights, deduplication, and thresholding."""

from services.dribbble.candidate import DesignCandidate, deduplicate_candidates
from services.dribbble.ranker import DesignRanker
from services.website_analysis.models import WebsiteAnalysis


def test_deduplicate_candidates_removes_duplicate_urls_and_images():
    cands = [
        DesignCandidate(
            id="c1",
            title="SaaS Hero 1",
            url="https://dribbble.com/shots/1",
            image_url="https://images.example.com/1.jpg",
            author="Author 1",
        ),
        DesignCandidate(
            id="c2",
            title="SaaS Hero 1 Duplicate",
            url="https://dribbble.com/shots/1/",  # Trailing slash duplicate
            image_url="https://images.example.com/different.jpg",
            author="Author 1",
        ),
        DesignCandidate(
            id="c3",
            title="Different Shot Same Image",
            url="https://dribbble.com/shots/2",
            image_url="https://images.example.com/1.jpg",  # Image duplicate
            author="Author 2",
        ),
        DesignCandidate(
            id="c4",
            title="Unique Shot",
            url="https://dribbble.com/shots/3",
            image_url="https://images.example.com/3.jpg",
            author="Author 3",
        ),
    ]

    unique = deduplicate_candidates(cands)
    assert len(unique) == 2
    assert unique[0].id == "c1"
    assert unique[1].id == "c4"


def test_weighted_scoring_formula_and_ordering():
    ranker = DesignRanker()
    analysis = WebsiteAnalysis(
        url="https://example-saas.com",
        industry="Software & Technology",
        category="SaaS Platform",
        target_audience="B2B",
        brand_personality="innovative & technical",
        key_sections=["hero", "features", "pricing"],
    )

    high_fit = DesignCandidate(
        id="high_fit",
        title="B2B SaaS Platform Analytics & Pricing Grid",
        url="https://dribbble.com/shots/high",
        image_url="https://images.example.com/high.jpg",
        author="Apex Studio",
        tags=["saas", "software", "pricing", "b2b", "glassmorphism", "clean", "ui"],
        color_palette=["#0F172A", "#6366F1"],
    )

    unrelated_fit = DesignCandidate(
        id="unrelated",
        title="Cute Cartoon Cat Character Illustration",
        url="https://dribbble.com/shots/cat",
        image_url="https://images.example.com/cat.jpg",
        author="Artist Cat",
        tags=["cat", "illustration", "drawing", "pencil"],
        color_palette=[],
    )

    ranked = ranker.rank([unrelated_fit, high_fit], analysis)
    assert len(ranked) == 2
    assert ranked[0].id == "high_fit"
    assert ranked[0].overall_score > 0.80

    # Verify formula calculation: 0.30*ind + 0.20*style + 0.20*mod + 0.15*layout + 0.15*brand
    expected_score = round(
        0.30 * ranked[0].industry_score
        + 0.20 * ranked[0].style_score
        + 0.20 * ranked[0].modernity_score
        + 0.15 * ranked[0].layout_score
        + 0.15 * ranked[0].brand_compatibility_score,
        3,
    )
    assert abs(ranked[0].overall_score - expected_score) < 0.001


def test_low_score_triggers_needs_review():
    ranker = DesignRanker()
    analysis = WebsiteAnalysis(
        url="https://enterprise-heavy-industry.com",
        industry="Heavy Machinery & Industrial Manufacturing",
        category="Industrial Equipment",
    )

    poor_candidate = DesignCandidate(
        id="poor",
        title="Kawaii Pastel Stickers Pack",
        url="https://dribbble.com/shots/stickers",
        image_url="https://images.example.com/stickers.jpg",
        author="Pastel Artist",
        tags=["stickers", "cute", "sketch"],
        color_palette=[],
    )

    best, needs_review = ranker.select_best([poor_candidate], analysis)
    assert best is not None
    assert best.overall_score < 0.60
    assert needs_review is True


def test_personal_portfolio_excluded():
    from services.dribbble.candidate import is_personal_or_excluded_reference

    personal_candidate = DesignCandidate(
        id="dribbble_24009083",
        title="News Website Design",
        url="https://dribbble.com/shots/24009083-News-Website-Design",
        image_url="https://cdn.dribbble.com/userupload/24009083/file/original.png",
        author="Jamaica Salem",
        tags=["news", "website", "design"],
        color_palette=["#000000"],
    )

    assert is_personal_or_excluded_reference(personal_candidate) is True

    valid_candidate = DesignCandidate(
        id="dribbble_logistics_01",
        title="FleetFlow - Logistics, Supply Chain & Telematics Platform",
        url="https://dribbble.com/shots/23819204-Logistics-Fleet-Tracking-Platform",
        image_url="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d",
        author="Nexus Studio",
        tags=["logistics", "shipping", "supply-chain"],
        color_palette=["#0F172A", "#3B82F6"],
    )

    assert is_personal_or_excluded_reference(valid_candidate) is False

    # Verify deduplicate_candidates filters it out
    filtered = deduplicate_candidates([personal_candidate, valid_candidate])
    assert len(filtered) == 1
    assert filtered[0].id == "dribbble_logistics_01"

    # Verify ranker filters it out
    ranker = DesignRanker()
    analysis = WebsiteAnalysis(
        url="https://example.com/logistics",
        industry="Logistics & Supply Chain",
        category="Freight",
    )
    ranked = ranker.rank([personal_candidate, valid_candidate], analysis)
    assert len(ranked) == 1
    assert ranked[0].id == "dribbble_logistics_01"

