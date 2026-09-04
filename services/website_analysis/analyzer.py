"""HTTP-based website analyzer extracting 15 dimensions of layout and styling."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import httpx

from services.website_analysis.models import WebsiteAnalysis
from utils.logger import logger


class HttpWebsiteAnalyzer:
    """Analyzes live websites to extract typography, color palettes, industry,
    structure, layout patterns, and responsiveness.
    """

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def analyze(
        self, url: str, business_name: Optional[str] = None
    ) -> WebsiteAnalysis:
        """Inspect the target website URL and extract analysis dimensions.
        
        Falls back to offline heuristic analysis if the site is unreachable.
        """
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        html_content = ""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers=self.headers,
                verify=False,  # Permissive SSL for legacy client websites
            ) as client:
                response = await client.get(clean_url)
                if response.status_code == 200:
                    html_content = response.text
                else:
                    logger.warning(
                        f"Website returned status {response.status_code} for {clean_url}. Using fallback analysis."
                    )
        except Exception as exc:
            logger.warning(
                f"Failed to fetch live website {clean_url}: {exc}. Using fallback analysis."
            )

        if html_content:
            return self.parse_html(html_content, clean_url, business_name=business_name)
        else:
            return self._build_fallback_analysis(clean_url, business_name=business_name)

    def parse_html(
        self, html: str, url: str, business_name: Optional[str] = None
    ) -> WebsiteAnalysis:
        """Parse HTML string and extract all 15 analysis dimensions."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Title & Meta
        title_tag = soup.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""

        meta_desc = ""
        desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        if desc_tag and desc_tag.get("content"):
            meta_desc = desc_tag["content"].strip()

        # Business name detection
        detected_name = business_name
        if not detected_name:
            site_name_tag = soup.find("meta", attrs={"property": "og:site_name"})
            if site_name_tag and site_name_tag.get("content"):
                detected_name = site_name_tag["content"].strip()
            elif raw_title:
                # E.g. "Acme Corp - Cloud Solutions" -> "Acme Corp"
                parts = re.split(r"[-|•:]", raw_title)
                if parts:
                    detected_name = parts[0].strip()

        # 2. Text Corpus for Industry & Keyword Classification
        h1_texts = [h.get_text(strip=True) for h in soup.find_all("h1")]
        h2_texts = [h.get_text(strip=True) for h in soup.find_all("h2")]
        body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
        combined_text = f"{raw_title} {meta_desc} {' '.join(h1_texts)} {' '.join(h2_texts)} {body_text[:2000]}".lower()

        # 3. Industry & Category classification
        industry, category, target_audience, brand_personality = self._classify_industry(
            combined_text, url
        )

        # 4. Color Palette Detection
        colors = self._extract_colors(html, soup)

        # 5. Typography style
        typography = self._extract_typography(html, soup)

        # 6. Key sections & Layout patterns
        key_sections = self._detect_sections(soup)

        # 7. Content density
        word_count = len(body_text.split())
        if word_count < 300:
            content_density = "minimal"
        elif word_count > 1200:
            content_density = "dense"
        else:
            content_density = "moderate"

        # 8. Mobile responsiveness indicators
        viewport_tag = soup.find("meta", attrs={"name": "viewport"})
        mobile_responsive = viewport_tag is not None

        # 9. Imagery style
        imagery_style = self._detect_imagery_style(soup)

        # 10. Functional requirements
        functional_requirements = self._detect_functional_requirements(soup)

        # 11. Visual strengths and weaknesses
        strengths, weaknesses, redesign_opportunities = self._evaluate_visual_aspects(
            soup=soup,
            mobile_responsive=mobile_responsive,
            key_sections=key_sections,
            colors=colors,
            word_count=word_count,
        )

        # 12. Navigation and Content structure
        nav_items = [
            a.get_text(strip=True)
            for a in soup.find_all("a")
            if a.parent and a.parent.name in ("nav", "li") and len(a.get_text(strip=True)) < 30
        ][:8]
        content_structure: Dict[str, Any] = {
            "h1_headings": h1_texts[:3],
            "nav_items": [n for n in nav_items if n],
            "total_word_count": word_count,
            "has_footer": bool(soup.find("footer")),
        }

        summary = (
            f"Website analysis for {url} ({industry} - {category}): "
            f"Target audience: {target_audience}, layout: {content_density} density with {len(key_sections)} key sections. "
            f"Brand tone: {brand_personality}."
        )

        suggested_improvements = [
            f"Implement a high-converting {category.lower()} hero with clear CTA",
            "Modernize color hierarchy with tailored contrast and clean accents",
            "Structure content into scannable feature grids and social proof cards",
        ]
        if not mobile_responsive:
            suggested_improvements.append("Rebuild viewport meta and responsive mobile navigation")

        return WebsiteAnalysis(
            url=url,
            business_name=detected_name,
            industry=industry,
            category=category,
            target_audience=target_audience,
            content_density=content_density,
            detected_colors=colors,
            typography_style=typography,
            key_sections=key_sections,
            imagery_style=imagery_style,
            brand_personality=brand_personality,
            mobile_responsive=mobile_responsive,
            visual_strengths=strengths,
            visual_weaknesses=weaknesses,
            redesign_opportunities=redesign_opportunities,
            functional_requirements=functional_requirements,
            content_structure=content_structure,
            summary=summary,
            suggested_improvements=suggested_improvements,
            offline_fallback=False,
            raw_title=raw_title,
            meta_description=meta_desc,
        )

    def _classify_industry(self, text: str, url: str) -> tuple[str, str, str, str]:
        """Classify industry, category, audience, and personality from text signals."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        patterns = [
            (
                r"\b(shop|store|cart|checkout|products|apparel|clothing|shoes|jewelry|ecommerce|merchandise)\b",
                "E-Commerce & Retail",
                "E-Commerce Store",
                "B2C",
                "vibrant & transactional",
            ),
            (
                r"\b(software|saas|api|platform|cloud|analytics|dashboard|ai|developer|automation|workflow)\b",
                "Software & Technology",
                "SaaS Platform",
                "B2B",
                "innovative & technical",
            ),
            (
                r"\b(clinic|health|dental|medical|doctor|patient|care|wellness|hospital|therapy|surgery)\b",
                "Healthcare & Wellness",
                "Medical Clinic",
                "B2C",
                "trustworthy & empathetic",
            ),
            (
                r"\b(bank|invest|financial|fintech|wealth|loan|credit|insurance|crypto|capital|accounting)\b",
                "Finance & Fintech",
                "Financial Services",
                "B2B",
                "authoritative & secure",
            ),
            (
                r"\b(estate|property|realty|homes|realtor|apartments|leasing|commercial real estate)\b",
                "Real Estate & Architecture",
                "Real Estate Agency",
                "B2C",
                "aspirational & elegant",
            ),
            (
                r"\b(agency|creative|studio|branding|marketing|advertising|production|design agency)\b",
                "Design & Marketing",
                "Creative Agency",
                "B2B",
                "bold & creative",
            ),
            (
                r"\b(restaurant|cafe|dining|menu|catering|bistro|bar|food|cuisine|bakery)\b",
                "Food & Hospitality",
                "Restaurant & Dining",
                "B2C",
                "welcoming & sensory",
            ),
            (
                r"\b(law|attorney|legal|counsel|lawyer|litigation|court)\b",
                "Legal & Advisory",
                "Law Firm",
                "B2B",
                "prestigious & authoritative",
            ),
            (
                r"\b(construction|contractor|roofing|plumbing|electrician|hvac|builder|remodel)\b",
                "Construction & Trade Services",
                "Local Service Contractor",
                "B2C",
                "dependable & straightforward",
            ),
        ]

        for regex, ind, cat, aud, tone in patterns:
            if re.search(regex, text) or re.search(regex, domain):
                return ind, cat, aud, tone

        # Default fallback
        return (
            "Technology & Business Services",
            "Corporate Website",
            "B2B",
            "professional & modern",
        )

    def _extract_colors(self, html: str, soup: BeautifulSoup) -> List[str]:
        """Extract dominant hex colors from CSS styles and inline styles."""
        hex_pattern = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
        found_hex = set(hex_pattern.findall(html))

        # Filter out common extremes (pure white #fff / pure black #000) for distinct palette
        palette = []
        for color in found_hex:
            norm = color.upper()
            if len(norm) == 4:
                # Expand #abc to #AABBCC
                norm = f"#{norm[1]*2}{norm[2]*2}{norm[3]*2}"
            if norm not in ("#FFFFFF", "#000000", "#111111", "#EEEEEE") and norm not in palette:
                palette.append(norm)

        # Provide harmonious defaults if no distinctive colors detected
        if not palette:
            palette = ["#0F172A", "#3B82F6", "#10B981"]

        return palette[:5]

    def _extract_typography(self, html: str, soup: BeautifulSoup) -> str:
        """Infer typography style from font links and CSS declarations."""
        html_lower = html.lower()
        if "serif" in html_lower and ("playfair" in html_lower or "merriweather" in html_lower or "georgia" in html_lower):
            return "editorial-serif"
        elif "mono" in html_lower or "fira code" in html_lower:
            return "technical-monospace"
        elif "inter" in html_lower or "roboto" in html_lower or "system-ui" in html_lower or "sans-serif" in html_lower:
            return "modern-sans-serif"
        return "clean-sans-serif"

    def _detect_sections(self, soup: BeautifulSoup) -> List[str]:
        """Detect key page layout sections."""
        detected = []
        section_identifiers = [
            ("hero", ["hero", "banner", "jumbotron"]),
            ("features", ["feature", "highlights", "benefits"]),
            ("services", ["service", "solutions", "offerings"]),
            ("about", ["about", "company", "story", "mission"]),
            ("portfolio", ["portfolio", "projects", "work", "case-stud"]),
            ("pricing", ["pricing", "plans", "tier", "subscription"]),
            ("testimonials", ["testimonial", "review", "social-proof", "customer"]),
            ("faq", ["faq", "frequently-asked", "questions", "accordion"]),
            ("contact", ["contact", "get-in-touch", "reach-us", "map"]),
            ("footer", ["footer", "site-footer", "copyright"]),
        ]

        page_tags = soup.find_all(["section", "div", "header", "footer"])
        for section_name, keywords in section_identifiers:
            found = False
            for tag in page_tags:
                tag_id = (tag.get("id") or "").lower()
                tag_cls = " ".join(tag.get("class") or []).lower()
                if any(kw in tag_id or kw in tag_cls for kw in keywords):
                    detected.append(section_name)
                    found = True
                    break
            if not found and section_name in ("hero", "features", "footer"):
                # Always assume core structure exists
                detected.append(section_name)

        # Deduplicate while preserving order
        return list(dict.fromkeys(detected))

    def _detect_imagery_style(self, soup: BeautifulSoup) -> str:
        """Analyze imagery style based on images, SVGs, and graphics."""
        svg_count = len(soup.find_all("svg"))
        img_count = len(soup.find_all("img"))

        if svg_count > img_count * 2:
            return "icon-and-vector-heavy"
        elif img_count > 10:
            return "rich-photography"
        elif img_count == 0 and svg_count == 0:
            return "minimal-typographic"
        return "mixed-photography-and-icons"

    def _detect_functional_requirements(self, soup: BeautifulSoup) -> List[str]:
        """Identify functional UI components required by the website."""
        reqs = []
        if soup.find("form"):
            reqs.append("contact-lead-form")
        if soup.find("input", attrs={"type": "search"}):
            reqs.append("search-bar")
        if any("cart" in (elem.get("class") or []) for elem in soup.find_all(["a", "button", "div"])):
            reqs.append("shopping-cart")
        if any("modal" in (elem.get("class") or []) for elem in soup.find_all(["div"])):
            reqs.append("interactive-modals")
        if any("pricing" in (elem.get("id") or "") for elem in soup.find_all(["section", "div"])):
            reqs.append("pricing-table")
        if not reqs:
            reqs.append("lead-capture-cta")
        return reqs

    def _evaluate_visual_aspects(
        self,
        soup: BeautifulSoup,
        mobile_responsive: bool,
        key_sections: List[str],
        colors: List[str],
        word_count: int,
    ) -> tuple[List[str], List[str], List[str]]:
        """Evaluate strengths, weaknesses, and redesign opportunities."""
        strengths = []
        weaknesses = []
        opportunities = []

        if mobile_responsive:
            strengths.append("Responsive viewport configuration is present")
        else:
            weaknesses.append("Missing mobile viewport meta tag")

        if len(key_sections) >= 4:
            strengths.append(f"Comprehensive section structure ({', '.join(key_sections[:4])})")
        else:
            weaknesses.append("Flat or monolithic page hierarchy lacking distinct sections")

        if word_count > 1500:
            weaknesses.append("Dense text blocks without adequate visual pacing or whitespace")
            opportunities.append("Condense long text into scannable feature cards with icons")
        elif word_count < 100:
            weaknesses.append("Sparse value proposition copy")

        if len(colors) >= 2:
            strengths.append(f"Identifiable brand colors ({colors[0]}, {colors[1]})")

        opportunities.extend([
            "Design modern high-contrast hero section with animated CTA and proof badges",
            "Implement glassmorphic content cards with hover elevation",
            "Add streamlined sticky navigation bar with prominent contact action",
        ])

        return strengths, weaknesses, opportunities

    def _build_fallback_analysis(
        self, url: str, business_name: Optional[str] = None
    ) -> WebsiteAnalysis:
        """Create a resilient baseline analysis when a website cannot be reached."""
        parsed = urlparse(url)
        domain = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
        clean_domain = domain.replace("www.", "")

        # Infer name from domain if not provided
        b_name = business_name
        if not b_name:
            b_name = clean_domain.split(".")[0].replace("-", " ").replace("_", " ").title()

        # Classify based on domain name keywords
        industry, category, audience, tone = self._classify_industry(clean_domain, url)

        return WebsiteAnalysis(
            url=url,
            business_name=b_name,
            industry=industry,
            category=category,
            target_audience=audience,
            content_density="moderate",
            detected_colors=["#0F172A", "#3B82F6", "#10B981"],
            typography_style="modern-sans-serif",
            key_sections=["hero", "features", "about", "testimonials", "contact", "footer"],
            imagery_style="photography",
            brand_personality=tone,
            mobile_responsive=True,
            visual_strengths=["Clean domain identity"],
            visual_weaknesses=["Original website was unreachable during live inspection"],
            redesign_opportunities=[
                "Establish modern flagship homepage with strong value proposition",
                "Incorporate modern card hierarchy and clean responsive layout",
            ],
            functional_requirements=["lead-capture-cta", "contact-form"],
            content_structure={
                "domain": domain,
                "note": "Constructed via offline architectural fallback",
            },
            summary=f"Offline baseline analysis for {url} ({industry} - {category}).",
            suggested_improvements=[
                "Build state-of-the-art responsive layout",
                "Apply modern color scheme with high visual clarity",
            ],
            offline_fallback=True,
            raw_title=f"{b_name} | {category}",
            meta_description=f"Official website for {b_name}.",
        )
