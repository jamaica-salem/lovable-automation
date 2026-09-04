"""High-level design search service orchestrating query generation, providers, and ranking."""

from typing import List, Optional, Tuple
from services.dribbble.candidate import DesignCandidate, deduplicate_candidates
from services.dribbble.interface import DesignReference, DesignSearchService
from services.dribbble.providers import CompositeSearchProvider, SearchProvider
from services.dribbble.query_generator import generate_search_queries
from services.dribbble.ranker import DesignRanker
from services.website_analysis.models import WebsiteAnalysis
from utils.logger import logger


class DribbbleDesignSearchService(DesignSearchService):
    """Orchestrates query generation, candidate search, deduplication, and ranking."""

    def __init__(
        self,
        provider: Optional[SearchProvider] = None,
        ranker: Optional[DesignRanker] = None,
    ):
        self.provider = provider or CompositeSearchProvider()
        self.ranker = ranker or DesignRanker()

    async def search_and_evaluate(
        self, analysis: WebsiteAnalysis
    ) -> Tuple[Optional[DesignCandidate], bool, List[DesignCandidate]]:
        """Run multi-query search, deduplicate candidates, and rank against analysis.
        
        Returns:
            (best_candidate, needs_review, all_ranked_candidates)
        """
        queries = generate_search_queries(analysis)
        all_candidates: List[DesignCandidate] = []

        for q in queries:
            try:
                results = await self.provider.search(q, limit=4)
                all_candidates.extend(results)
            except Exception as exc:
                logger.warning(f"Provider search failed for query '{q}': {exc}")

        unique_candidates = deduplicate_candidates(all_candidates)
        if not unique_candidates:
            logger.warning(f"No design candidates found for {analysis.url}")
            return None, True, []

        ranked = self.ranker.rank(unique_candidates, analysis)
        best, needs_review = self.ranker.select_best(ranked, analysis)
        return best, needs_review, ranked

    # Interface compatibility methods for DesignSearchService
    async def search_references(self, industry: str, category: str) -> List[DesignReference]:
        # Minimal analysis baseline for compatibility
        analysis = WebsiteAnalysis(
            url="https://placeholder.internal",
            industry=industry,
            category=category,
        )
        _, _, ranked = await self.search_and_evaluate(analysis)
        return [
            DesignReference(
                reference_id=c.id,
                title=c.title,
                source=c.source,
                url=c.url,
                image_url=c.image_url,
                author=c.author,
                tags=c.tags,
                color_palette=c.color_palette,
                suitability_score=c.overall_score,
                rationale=c.evaluation_notes,
            )
            for c in ranked
        ]

    async def evaluate_and_select_best(
        self, references: List[DesignReference], industry: str
    ) -> DesignReference:
        if not references:
            raise ValueError("No references to evaluate")
        return max(references, key=lambda r: r.suitability_score)
