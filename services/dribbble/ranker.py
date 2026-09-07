"""Candidate evaluation and weighted multi-criteria ranking."""

from typing import List, Optional, Tuple
from services.dribbble.candidate import DesignCandidate, is_personal_or_excluded_reference
from services.website_analysis.models import WebsiteAnalysis


class DesignRanker:
    """Evaluates design reference candidates against website analysis using a
    5-criteria weighted scoring formula.
    
    Formula:
        Overall = (0.30 * Industry) + (0.20 * Style) + (0.20 * Modernity)
                + (0.15 * Layout) + (0.15 * Brand Compatibility)
    
    Threshold:
        Overall < 0.60 -> flag as needs_review (triggers DESIGN_NEEDS_REVIEW).
    """

    REVIEW_THRESHOLD: float = 0.55

    def rank(
        self, candidates: List[DesignCandidate], analysis: WebsiteAnalysis
    ) -> List[DesignCandidate]:
        """Score and sort all candidates descending by overall weighted score, excluding user personal uploads."""
        scored: List[DesignCandidate] = []
        for cand in candidates:
            if is_personal_or_excluded_reference(cand):
                continue

            ind_score = self._score_industry(cand, analysis)
            style_score = self._score_style(cand, analysis)
            mod_score = self._score_modernity(cand)
            layout_score = self._score_layout(cand, analysis)
            brand_score = self._score_brand(cand, analysis)

            overall = (
                0.30 * ind_score
                + 0.20 * style_score
                + 0.20 * mod_score
                + 0.15 * layout_score
                + 0.15 * brand_score
            )
            overall = round(overall, 3)

            cand.industry_score = ind_score
            cand.style_score = style_score
            cand.modernity_score = mod_score
            cand.layout_score = layout_score
            cand.brand_compatibility_score = brand_score
            cand.overall_score = overall
            cand.evaluation_notes = (
                f"Overall: {overall:.2f} | Industry ({ind_score:.2f}), Style ({style_score:.2f}), "
                f"Modernity ({mod_score:.2f}), Layout ({layout_score:.2f}), Brand ({brand_score:.2f})."
            )
            scored.append(cand)

        scored.sort(key=lambda c: c.overall_score, reverse=True)
        return scored

    def select_best(
        self, candidates: List[DesignCandidate], analysis: WebsiteAnalysis
    ) -> Tuple[Optional[DesignCandidate], bool]:
        """Select top candidate and check against minimum quality threshold.
        
        Returns:
            (best_candidate, needs_review)
        """
        if not candidates:
            return None, True

        ranked = self.rank(candidates, analysis)
        if not ranked:
            return None, True

        best = ranked[0]
        needs_review = best.overall_score < self.REVIEW_THRESHOLD
        return best, needs_review

    def _score_industry(self, cand: DesignCandidate, analysis: WebsiteAnalysis) -> float:
        """Industry match (0.30 weight) - domain alignment is strictly prioritized."""
        cand_text = f"{cand.title} {' '.join(cand.tags)}".lower()
        ind_tokens = [t for t in analysis.industry.lower().split() if len(t) > 2]
        cat_tokens = [t for t in analysis.category.lower().split() if len(t) > 2]
        b_name_tokens = [t for t in (analysis.business_name or "").lower().split() if len(t) > 2]

        stop_words = {"and", "the", "services", "corporate", "website", "global", "group", "ltd", "inc", "co", "company"}
        search_tokens = set(ind_tokens + cat_tokens + b_name_tokens) - stop_words

        match_count = sum(1 for token in search_tokens if token in cand_text)

        if match_count >= 2:
            return 1.0
        elif match_count == 1:
            return 0.90
        return 0.10

    def _score_style(self, cand: DesignCandidate, analysis: WebsiteAnalysis) -> float:
        """Style alignment (0.20 weight)."""
        cand_text = f"{cand.title} {' '.join(cand.tags)}".lower()
        personality_tokens = analysis.brand_personality.lower().split()

        style_match = 0.60
        for token in personality_tokens:
            if len(token) > 3 and token in cand_text:
                style_match += 0.15

        if analysis.content_density == "minimal" and "minimal" in cand_text:
            style_match += 0.15

        if any(t in cand_text for t in ("clean", "modern", "sleek", "editorial", "dark-mode", "b2b", "vitality")):
            style_match = max(style_match, 0.80)

        return min(1.0, round(style_match, 2))

    def _score_modernity(self, cand: DesignCandidate) -> float:
        """Modernity score (0.20 weight) based on contemporary UI patterns."""
        cand_text = f"{cand.title} {' '.join(cand.tags)}".lower()
        modern_indicators = [
            "clean", "glassmorphism", "dark-mode", "dashboard", "minimal",
            "sleek", "modern-typography", "card", "grid", "hero", "b2b", "ui",
            "web", "landing", "interface", "telematics", "portal",
        ]
        hits = sum(1 for ind in modern_indicators if ind in cand_text)
        if hits >= 3:
            return 0.95
        elif hits >= 1:
            return 0.80
        return 0.35

    def _score_layout(self, cand: DesignCandidate, analysis: WebsiteAnalysis) -> float:
        """Layout fit (0.15 weight)."""
        cand_text = f"{cand.title} {' '.join(cand.tags)}".lower()
        section_hits = 0
        for sec in analysis.key_sections:
            if sec in cand_text:
                section_hits += 1

        layout_keywords = (
            "landing", "dashboard", "platform", "portal", "store", "showcase",
            "telematics", "tracking", "calculator", "quote", "booking", "cart",
            "pricing", "website", "web", "ui", "interface"
        )
        if section_hits >= 2 or any(k in cand_text for k in ("landing page", "dashboard", "portal", "showcase", "platform")):
            return 0.95
        elif section_hits == 1 or any(k in cand_text for k in layout_keywords):
            return 0.85
        return 0.50

    def _score_brand(self, cand: DesignCandidate, analysis: WebsiteAnalysis) -> float:
        """Brand compatibility (0.15 weight)."""
        if cand.color_palette:
            return 0.85
        if cand.image_url:
            return 0.75
        return 0.50

