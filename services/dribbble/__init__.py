"""Dribbble design reference search and ranking package."""

from services.dribbble.candidate import DesignCandidate, deduplicate_candidates
from services.dribbble.interface import (
    DesignReference,
    DesignSearchService,
    StubDesignSearchService,
)
from services.dribbble.providers import (
    CompositeSearchProvider,
    DribbbleApiSearchProvider,
    MockSearchProvider,
    SearchProvider,
)
from services.dribbble.query_generator import generate_search_queries
from services.dribbble.ranker import DesignRanker
from services.dribbble.service import DribbbleDesignSearchService

__all__ = [
    "DesignCandidate",
    "deduplicate_candidates",
    "DesignReference",
    "DesignSearchService",
    "StubDesignSearchService",
    "SearchProvider",
    "DribbbleApiSearchProvider",
    "MockSearchProvider",
    "CompositeSearchProvider",
    "generate_search_queries",
    "DesignRanker",
    "DribbbleDesignSearchService",
]
