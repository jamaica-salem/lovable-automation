"""Search providers for modern design references."""

from abc import ABC, abstractmethod
import hashlib
from typing import List, Optional
import httpx

from app.config import settings
from services.dribbble.candidate import DesignCandidate
from utils.logger import logger


class SearchProvider(ABC):
    """Abstract interface for design reference search providers."""

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        """Execute a search query and return candidate design references."""
        pass


class DribbbleApiSearchProvider(SearchProvider):
    """Provider connecting to the official Dribbble API v2.
    
    Filters authenticated user's portfolio shots by query keywords if present.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.dribbble_access_token
        self.base_url = "https://api.dribbble.com/v2"

    async def search(self, query: str, limit: int = 5) -> List[DesignCandidate]:
        """Search Dribbble via official API endpoints."""
        if not self.access_token:
            logger.debug("No Dribbble access token configured. Skipping Dribbble API search.")
            return []

        headers = {"Authorization": f"Bearer {self.access_token}"}
        q_tokens = [t.lower() for t in query.split() if len(t) > 2]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/user/shots",
                    headers=headers,
                    params={"per_page": 20},
                )
                if response.status_code != 200:
                    logger.warning(
                        f"Dribbble API returned status {response.status_code}: {response.text[:200]}"
                    )
                    return []

                data = response.json()
                candidates = []
                for item in data:
                    item_text = f"{item.get('title', '')} {' '.join(item.get('tags') or [])} {item.get('description', '')}".lower()
                    # Only include user shots if they legitimately match the website's query keywords
                    if q_tokens and not any(token in item_text for token in q_tokens):
                        continue

                    images = item.get("images") or {}
                    img_url = (
                        images.get("hidpi")
                        or images.get("normal")
                        or images.get("teaser")
                        or ""
                    )
                    candidates.append(
                        DesignCandidate(
                            id=f"dribbble_{item.get('id', '')}",
                            title=item.get("title", "Modern Web UI"),
                            url=item.get("html_url", ""),
                            image_url=img_url,
                            author=item.get("user", {}).get("name", "Dribbble Designer"),
                            source="dribbble",
                            tags=item.get("tags") or [],
                            color_palette=[],
                        )
                    )
                return candidates[:limit]
        except Exception as exc:
            logger.warning(f"Error querying Dribbble API: {exc}")
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
            "tags": ["logistics", "freight", "transport", "shipping", "supply-chain", "tracking-widget", "fleet", "telematics", "dark-mode", "b2b"],
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
            "tags": ["cargo", "freight", "logistics", "shipping", "rate-calculator", "supply", "transport", "ocean-air", "b2b"],
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
            "tags": ["saas", "fintech", "dashboard", "dark-mode", "b2b", "analytics", "finance"],
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
            "tags": ["healthcare", "medical", "clinic", "wellness", "clean", "b2c", "booking"],
            "color_palette": ["#FFFFFF", "#0EA5E9", "#14B8A6", "#F1F5F9"],
            "category": "clinic",
            "industry": "healthcare",
        },
        {
            "id": "mock_ecommerce_01",
            "title": "Minimalist High-Fashion Apparel & Home Store",
            "url": "https://dribbble.com/shots/23729103-Minimal-Apparel-Store",
            "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1200",
            "author": "Nordic Atelier",
            "tags": ["ecommerce", "store", "apparel", "minimal", "editorial", "b2c", "cart"],
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
            "tags": ["agency", "creative", "portfolio", "bold-typography", "b2b", "showcase"],
            "color_palette": ["#09090B", "#F43F5E", "#E11D48", "#FFFFFF"],
            "category": "agency",
            "industry": "design",
        },
        {
            "id": "mock_realestate_01",
            "title": "Luxury Real Estate & Architectural Property Showcase",
            "url": "https://dribbble.com/shots/23940192-Luxury-Architecture-Estates",
            "image_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200",
            "author": "Arch & Stone",
            "tags": ["real-estate", "architecture", "luxury", "property", "b2c", "editorial"],
            "color_palette": ["#F8F9FA", "#1E293B", "#D97706", "#334155"],
            "category": "real-estate",
            "industry": "property",
        },
        {
            "id": "mock_trade_01",
            "title": "Dependable Local Contractor & Trade Services",
            "url": "https://dribbble.com/shots/23491024-Contractor-Construction-UI",
            "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=1200",
            "author": "Solid Builders Co",
            "tags": ["contractor", "construction", "services", "quote-calculator", "local", "trades"],
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

            results.append(
                DesignCandidate(
                    id=item["id"],
                    title=item["title"],
                    url=item["url"],
                    image_url=item["image_url"],
                    author=item["author"],
                    source="dribbble",
                    tags=item["tags"],
                    color_palette=item["color_palette"],
                )
            )
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
