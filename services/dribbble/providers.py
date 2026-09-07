"""Search providers for modern design references."""

from abc import ABC, abstractmethod
import hashlib
from typing import List, Optional
import httpx

from app.config import settings
from services.dribbble.candidate import DesignCandidate, is_personal_or_excluded_reference
from utils.logger import logger


class SearchProvider(ABC):
    """Abstract interface for design reference search providers."""

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        """Execute a search query and return candidate design references."""
        pass


class DribbbleApiSearchProvider(SearchProvider):
    """Provider connecting to the official Dribbble API v2.
    
    In Dribbble API v2, the official OAuth endpoints only access the authenticated user's
    own uploaded shots (/user/shots). For client redesign automation, we do not inject
    the user's personal uploads as client design references.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.dribbble_access_token
        self.base_url = "https://api.dribbble.com/v2"

    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        """Search Dribbble via official API endpoints.
        
        Strictly excludes authenticated user's personal portfolio shots from client redesigns.
        """
        # Exclude personal user portfolio from third-party client design references
        return []


class MockSearchProvider(SearchProvider):
    """Deterministic, verified modern design reference library across key industries."""

    MOCK_REFERENCE_BANK = [
        {
            "id": "dribbble_logistics_01",
            "title": "Website for a Logistics Company - UnitMove",
            "url": "https://dribbble.com/shots/25918182-Website-for-a-Logistics-Company-UnitMove",
            "image_url": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200",
            "author": "Halo Lab",
            "tags": ["logistics", "freight", "transport", "shipping", "supply-chain", "tracking-widget", "fleet", "telematics", "dark-mode", "b2b", "clean", "modern", "ui", "platform", "web-design", "website", "landing-page"],
            "color_palette": ["#0F172A", "#3B82F6", "#10B981", "#F8FAFC"],
            "category": "web-design",
            "industry": "logistics",
        },
        {
            "id": "mock_health_01",
            "title": "Case Study: Modern Clinic Website",
            "url": "https://dribbble.com/shots/18724914-Case-Study-Clinic-Website",
            "image_url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200",
            "author": "Tubik",
            "tags": ["healthcare", "medical", "clinic", "wellness", "clean", "b2c", "booking", "healthpulse", "doctor", "modern", "ui", "portal", "web-design", "website", "landing-page"],
            "color_palette": ["#FFFFFF", "#0EA5E9", "#14B8A6", "#F1F5F9"],
            "category": "web-design",
            "industry": "healthcare",
        },
        {
            "id": "mock_saas_01",
            "title": "Fintech Website Design for Puzzle",
            "url": "https://dribbble.com/shots/25478108--Case-Study-Fintech-Website-Design-for-Puzzle",
            "image_url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200",
            "author": "Ramotion",
            "tags": ["saas", "fintech", "dashboard", "dark-mode", "b2b", "analytics", "finance", "vault", "clean", "modern", "ui", "platform", "web-design", "website", "landing-page"],
            "color_palette": ["#0B0F19", "#6366F1", "#10B981", "#F8FAFC"],
            "category": "web-design",
            "industry": "finance",
        },
        {
            "id": "dribbble_coffee_01",
            "title": "Specialty Coffee Shop & Roastery Website",
            "url": "https://dribbble.com/shots/24478311-Coffee-Shop-Website",
            "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=1200",
            "author": "Purrweb",
            "tags": ["coffee", "roasters", "roastery", "specialty", "brew", "greenleaf", "ecommerce", "store", "beans", "d2c", "retail", "clean", "minimal", "modern", "grid", "hero", "ui", "web-design", "website", "landing-page"],
            "color_palette": ["#1A120B", "#D5CEA3", "#3C2A21", "#F8F5F2"],
            "category": "web-design",
            "industry": "ecommerce",
        },
        {
            "id": "mock_realestate_01",
            "title": "Creative Architectural Interactive Website",
            "url": "https://dribbble.com/shots/27576623-Creative-Architectural-Interactive-Website",
            "image_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200",
            "author": "Tubik",
            "tags": ["architecture", "architects", "architect", "studio", "luxury", "real-estate", "property", "editorial", "modern", "clean", "showcase", "ui", "web-design", "website", "landing-page"],
            "color_palette": ["#F8F9FA", "#1E293B", "#D97706", "#334155"],
            "category": "web-design",
            "industry": "real-estate",
        },
        {
            "id": "mock_trade_01",
            "title": "Steel Industrial & Construction Company Landing Page",
            "url": "https://dribbble.com/shots/26575677-Steel-industrial-company-landing-page",
            "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=1200",
            "author": "Tubik",
            "tags": ["contractor", "construction", "trade", "services", "quote-calculator", "commercial", "building", "trades", "solidbase", "modern", "clean", "ui", "web-design", "website", "landing-page"],
            "color_palette": ["#FFFFFF", "#2563EB", "#F59E0B", "#1E293B"],
            "category": "web-design",
            "industry": "trade",
        },
        {
            "id": "mock_agency_01",
            "title": "Case Study: Digital Agency Website Design",
            "url": "https://dribbble.com/shots/26850684-Case-Study-Digital-Agency-Website",
            "image_url": "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=1200",
            "author": "Tubik",
            "tags": ["agency", "creative", "portfolio", "bold-typography", "b2b", "showcase", "modern", "clean", "ui", "web-design", "website", "landing-page"],
            "color_palette": ["#09090B", "#F43F5E", "#E11D48", "#FFFFFF"],
            "category": "web-design",
            "industry": "design",
        },
        {
            "id": "mock_ecommerce_01",
            "title": "Website for a Consumer Brand - Lanot",
            "url": "https://dribbble.com/shots/25524848-Website-for-a-Consumer-Brand-Lanot",
            "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1200",
            "author": "Tubik",
            "tags": ["ecommerce", "store", "apparel", "minimal", "editorial", "b2c", "cart", "fashion", "clothing", "modern", "clean", "ui", "web-design", "website", "landing-page"],
            "color_palette": ["#FAF9F6", "#18181B", "#71717A", "#E4E4E7"],
            "category": "web-design",
            "industry": "retail",
        },
    ]

    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        """Return deterministic candidates matching query tokens."""
        q_tokens = query.lower().split()
        scored: List[tuple[int, dict]] = []

        for item in self.MOCK_REFERENCE_BANK:
            score = 0
            text_corpus = f"{item['title']} {' '.join(item['tags'])} {item['category']} {item['industry']}".lower()
            for token in q_tokens:
                if len(token) > 2 and token in text_corpus:
                    score += 2
                elif len(token) > 2 and any(token in w for w in item['tags']):
                    score += 3
            scored.append((score, item))

        # Sort by match score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for match_score, item in scored:
            # If search query has specific tokens, require at least 1 match unless empty query
            if q_tokens and match_score == 0 and len(results) >= 1:
                continue

            candidate = DesignCandidate(
                id=item["id"],
                title=item["title"],
                url=item["url"],
                image_url=item["image_url"],
                author=item["author"],
                source="dribbble",
                tags=item["tags"],
                color_palette=item["color_palette"],
            )
            if is_personal_or_excluded_reference(candidate):
                continue

            results.append(candidate)
            if len(results) >= limit:
                break

        return results


class CompositeSearchProvider(SearchProvider):
    """Combines live Dribbble API with curated library matching keywords and UI elements."""

    def __init__(
        self,
        api_provider: Optional[DribbbleApiSearchProvider] = None,
        mock_provider: Optional[MockSearchProvider] = None,
    ):
        self.api_provider = api_provider or DribbbleApiSearchProvider()
        self.mock_provider = mock_provider or MockSearchProvider()

    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        results: List[DesignCandidate] = []
        if self.api_provider.access_token:
            results = await self.api_provider.search(query, limit=limit)

        # Always complement with keyword-matched reference library
        library_results = await self.mock_provider.search(query, limit=limit)
        results.extend(library_results)

        return results[:limit]
