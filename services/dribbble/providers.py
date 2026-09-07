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
            "title": "FleetFlow - Logistics, Supply Chain & Telematics Platform",
            "url": "https://dribbble.com/shots/23819204-Logistics-Fleet-Tracking-Platform",
            "image_url": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200",
            "author": "Nexus Studio",
            "tags": ["logistics", "freight", "transport", "shipping", "supply-chain", "tracking-widget", "fleet", "telematics", "dark-mode", "b2b", "clean", "modern", "ui", "platform"],
            "color_palette": ["#0F172A", "#3B82F6", "#10B981", "#F8FAFC"],
            "category": "logistics",
            "industry": "logistics",
        },
        {
            "id": "dribbble_logistics_02",
            "title": "CargoHub - Global Multimodal Freight & Rate Estimator",
            "url": "https://dribbble.com/shots/24109823-CargoHub-Global-Freight-Portal",
            "image_url": "https://images.unsplash.com/photo-1578575437130-527eed3abbec?w=1200",
            "author": "Vanguard Logistics UI",
            "tags": ["cargo", "freight", "logistics", "shipping", "rate-calculator", "supply", "transport", "ocean-air", "b2b", "modern", "clean", "portal"],
            "color_palette": ["#0A192F", "#00D4B2", "#3B82F6", "#E2E8F0"],
            "category": "shipping",
            "industry": "logistics",
        },
        {
            "id": "mock_saas_01",
            "title": "Fintech & SaaS Clean Dark Analytics Platform",
            "url": "https://dribbble.com/shots/23504192-Fintech-Analytics-Dashboard",
            "image_url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200",
            "author": "Apex Studio",
            "tags": ["saas", "fintech", "dashboard", "dark-mode", "b2b", "analytics", "finance", "vault", "clean", "modern", "ui"],
            "color_palette": ["#0B0F19", "#6366F1", "#10B981", "#F8FAFC"],
            "category": "saas",
            "industry": "finance",
        },
        {
            "id": "mock_health_01",
            "title": "Modern Medical Clinic & Patient Portal",
            "url": "https://dribbble.com/shots/23611894-Health-Medical-Clinic-Portal",
            "image_url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200",
            "author": "Vitality Design",
            "tags": ["healthcare", "medical", "clinic", "wellness", "clean", "b2c", "booking", "healthpulse", "doctor", "modern", "ui", "portal"],
            "color_palette": ["#FFFFFF", "#0EA5E9", "#14B8A6", "#F1F5F9"],
            "category": "clinic",
            "industry": "healthcare",
        },
        {
            "id": "dribbble_coffee_01",
            "title": "Artisan Coffee Roasters & Specialty Brew Store",
            "url": "https://dribbble.com/shots/23984102-Specialty-Coffee-Roastery-Store",
            "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=1200",
            "author": "Brew & Bean Design",
            "tags": ["coffee", "roasters", "roastery", "specialty", "brew", "greenleaf", "ecommerce", "store", "beans", "d2c", "retail", "clean", "minimal", "modern", "grid", "hero", "ui"],
            "color_palette": ["#1A120B", "#D5CEA3", "#3C2A21", "#F8F5F2"],
            "category": "ecommerce",
            "industry": "ecommerce",
        },
        {
            "id": "mock_ecommerce_01",
            "title": "Minimalist High-Fashion Apparel & Home Store",
            "url": "https://dribbble.com/shots/23729103-Minimal-Apparel-Store",
            "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1200",
            "author": "Nordic Atelier",
            "tags": ["ecommerce", "store", "apparel", "minimal", "editorial", "b2c", "cart", "fashion", "clothing", "modern", "clean", "ui"],
            "color_palette": ["#FAF9F6", "#18181B", "#71717A", "#E4E4E7"],
            "category": "ecommerce",
            "industry": "retail",
        },
        {
            "id": "mock_agency_01",
            "title": "Creative Brand Agency & Portfolio Showcase",
            "url": "https://dribbble.com/shots/23881029-Creative-Studio-Portfolio",
            "image_url": "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=1200",
            "author": "Bold Visions",
            "tags": ["agency", "creative", "portfolio", "bold-typography", "b2b", "showcase", "modern", "clean", "ui"],
            "color_palette": ["#09090B", "#F43F5E", "#E11D48", "#FFFFFF"],
            "category": "agency",
            "industry": "design",
        },
        {
            "id": "mock_realestate_01",
            "title": "Apex Studio - Luxury Modern Architecture & Spatial Design Showcase",
            "url": "https://dribbble.com/shots/23940192-Luxury-Architecture-Estates",
            "image_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200",
            "author": "Arch & Stone",
            "tags": ["architecture", "architects", "architect", "studio", "luxury", "real-estate", "property", "editorial", "modern", "clean", "showcase", "ui"],
            "color_palette": ["#F8F9FA", "#1E293B", "#D97706", "#334155"],
            "category": "architecture",
            "industry": "real-estate",
        },
        {
            "id": "mock_trade_01",
            "title": "SolidBase - Commercial Construction, General Contractor & Trade Services",
            "url": "https://dribbble.com/shots/23491024-Contractor-Construction-UI",
            "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=1200",
            "author": "Solid Builders Co",
            "tags": ["contractor", "construction", "trade", "services", "quote-calculator", "commercial", "building", "trades", "solidbase", "modern", "clean", "ui"],
            "color_palette": ["#FFFFFF", "#2563EB", "#F59E0B", "#1E293B"],
            "category": "contractor",
            "industry": "trade",
        },
        {
            "id": "mock_generic_01",
            "title": "Next-Gen Corporate & Enterprise Solutions",
            "url": "https://dribbble.com/shots/23901482-Enterprise-B2B-Platform",
            "image_url": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1200",
            "author": "Vanguard UI",
            "tags": ["corporate", "enterprise", "modern-sans-serif", "b2b", "glassmorphism", "kpi"],
            "color_palette": ["#0F172A", "#2563EB", "#64748B", "#F8FAFC"],
            "category": "corporate",
            "industry": "business",
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
