"""Prompt builder for Lovable website redesign generation."""

from typing import Any, Dict, List, Optional
from prompts.reference_rules import REFERENCE_RULES_DIRECTIVE
from services.website_analysis.models import WebsiteAnalysis


class LovablePromptBuilder:
    """Constructs production-grade redesign prompts for Lovable.
    
    Guarantees that the design reference provides layout and structural inspiration
    while strictly preserving the original website's content, branding, and identity.
    """

    def build_redesign_prompt(
        self,
        website_url: str,
        business_name: Optional[str] = None,
        analysis: Optional[WebsiteAnalysis] = None,
        design_reference: Optional[Dict[str, Any]] = None,
        additional_instructions: Optional[str] = None,
    ) -> str:
        """Assemble structured redesign prompt with all required architectural boundaries."""
        b_name = business_name or (analysis.business_name if analysis else None) or "Target Business"
        industry = (analysis.industry if analysis else None) or "Technology & Services"
        category = (analysis.category if analysis else None) or "Corporate Website"
        target_audience = (analysis.target_audience if analysis else None) or "B2B"
        brand_tone = (analysis.brand_personality if analysis else None) or "modern and professional"

        # Extract detected color palette
        detected_colors = (analysis.detected_colors if analysis else None) or ["#0F172A", "#3B82F6", "#10B981"]
        colors_str = ", ".join(detected_colors)

        # Extract key sections and requirements
        key_sections = (analysis.key_sections if analysis else None) or [
            "hero", "features", "about", "testimonials", "contact", "footer"
        ]
        sections_str = ", ".join(key_sections)

        functional_reqs = (analysis.functional_requirements if analysis else None) or [
            "contact-lead-form", "lead-capture-cta"
        ]
        funcs_str = ", ".join(functional_reqs)

        # Reference details
        ref = design_reference or {}
        ref_title = ref.get("title") or ref.get("design_reference_title") or "Modern Aesthetic UI"
        ref_url = ref.get("url") or ref.get("design_reference_url") or "https://dribbble.com"
        ref_image = ref.get("image_url") or ref.get("design_reference_image") or ""
        ref_palette = ref.get("color_palette") or []
        ref_palette_str = ", ".join(ref_palette) if ref_palette else "Modern neutral dark/light surfaces"
        ref_tags = ref.get("tags") or ["modern", "clean", "responsive"]
        ref_tags_str = ", ".join(ref_tags)

        prompt_lines = [
            f"# REDESIGN SPECIFICATION: {b_name}",
            f"Original Website URL: {website_url}",
            f"Target Industry: {industry}",
            f"Website Category: {category}",
            f"Target Audience: {target_audience}",
            "",
            "## 1. BRAND IDENTITY & PRESERVATION REQUIREMENTS",
            f"- Company / Brand Name: {b_name}",
            f"- Brand Personality & Tone: {brand_tone}",
            f"- Authoritative Brand Colors: {colors_str}",
            "- CRITICAL RULE: PRESERVE ORIGINAL BRAND IDENTITY. Do NOT discard the client's existing brand name, logos, or primary color identity. Refine and modernize them with high visual contrast.",
            "- CRITICAL RULE: PRESERVE ORIGINAL CONTENT. All company information, value propositions, service descriptions, and contact points from the original website MUST be faithfully retained.",
            "",
            "## 2. STRUCTURAL & FUNCTIONAL SCOPE",
            f"- Key Page Sections to Build: {sections_str}",
            f"- Interactive UI & Functional Features: {funcs_str}",
            "- Ensure clear visual hierarchy with high-conversion CTAs and smooth scroll anchors.",
            "",
            "## 3. DESIGN INSPIRATION & REFERENCE PATTERNS",
            f"- Reference Title: {ref_title}",
            f"- Reference Link: {ref_url}",
        ]

        if ref_image:
            prompt_lines.append(f"- Reference Image Preview: {ref_image}")

        prompt_lines.extend([
            f"- Reference Aesthetic Tags: {ref_tags_str}",
            f"- Complementary Reference Accents: {ref_palette_str}",
            "",
            "## 4. STRICT REFERENCE UTILIZATION RULES",
            REFERENCE_RULES_DIRECTIVE,
            "- DO NOT copy the reference website's company name, brand logo, or specific business copy.",
            "- Use the reference strictly to guide layout spacing, card elevation, visual pacing, and modern typography.",
            "",
            "## 5. RESPONSIVE & MODERN UI EXCELLENCE",
            "- Mobile-First Architecture: Ensure 100% fluid responsiveness across mobile (375px+), tablet, and desktop (1440px+).",
            "- Modern Aesthetics: Incorporate clean sans-serif typography (e.g. Inter/Outfit), subtle glassmorphism cards, refined borders, and gentle hover micro-interactions.",
            "- Accessibility (a11y): Ensure high contrast ratios, semantic HTML5 tags (header, nav, main, section, footer), and descriptive ARIA labels.",
            "- No Placeholders: Generate full, polished UI components with complete styling rather than empty placeholder frames.",
        ])

        # Domain-specific conversion directives
        domain_directives = self._get_domain_directives(industry, category, target_audience)
        if domain_directives:
            prompt_lines.extend([
                "",
                "## 6. INDUSTRY & DOMAIN-SPECIFIC CONVERSION PATTERNS",
                domain_directives,
            ])

        if additional_instructions:
            prompt_lines.extend([
                "",
                "## 7. CLIENT SPECIFICATIONS & UNIQUE WEBSITE OBJECTIVES",
                f"- Specific Requirements: {additional_instructions.strip()}",
                "- Ensure the redesigned hero, feature grid, and CTAs directly incorporate and highlight these exact objectives.",
            ])

        return "\n".join(prompt_lines).strip()

    def _get_domain_directives(self, industry: str, category: str, target_audience: str) -> str:
        """Return tailored conversion patterns based on website industry and audience."""
        ind = (industry or "").lower()
        cat = (category or "").lower()

        if any(w in ind or w in cat for w in ("logistic", "freight", "transport", "shipping", "supply")):
            return (
                "- HERO FEATURE: Include an interactive real-time tracking search input ('Enter Tracking or Bill of Lading Number').\n"
                "- TELEMATICS & STATS: Display high-impact key metrics (e.g. 99.8% On-Time Delivery, Global Fleet Coverage, Real-Time Telematics).\n"
                "- QUOTE WIDGET: Provide an instant multi-step freight rate quote calculator.\n"
                "- COMPLIANCE & SAFETY: Highlight ISO, Customs-Trade Partnership, and safety certifications prominently."
            )

        if any(w in ind or w in cat for w in ("health", "clinic", "medical", "doctor", "dental", "care")):
            return (
                "- TRUST & ACCREDITATION: Prominently feature medical provider credentials, board certifications, and HIPAA compliance badges.\n"
                "- APPOINTMENT BOOKING: Implement a high-converting, friction-free 'Book Appointment / Consult' workflow.\n"
                "- SPECIALTIES & DOCTORS: Include doctor specialty cards with credentials, bios, and direct booking triggers.\n"
                "- PATIENT CARE: Provide an urgent care triage bar, patient portal quick-login, and clear insurance coverage overview."
            )

        if any(w in ind or w in cat for w in ("fintech", "finance", "bank", "invest", "wealth")):
            return (
                "- SECURITY & COMPLIANCE: Showcase bank-grade 256-bit encryption, SOC2 Type II, and regulatory compliance trust badges.\n"
                "- INTERACTIVE ROI / PRICING: Include interactive financial calculators or dynamic pricing tier comparisons.\n"
                "- METRICS DASHBOARD: Render a sleek, dark-mode preview of real-time account analytics, spending insights, and transaction graphs.\n"
                "- TRUST BUILDERS: Highlight institutional backing, audited security protocols, and client testimonial metrics."
            )

        if any(w in ind or w in cat for w in ("ecommerce", "coffee", "roast", "shop", "retail", "consumer", "d2c")):
            return (
                "- PRODUCT HIGHLIGHT: Feature a vibrant interactive product showcase with roast/size/variant selector and sticky cart CTA.\n"
                "- SUBSCRIPTION FLOW: Build an intuitive recurring subscription builder (e.g. Deliver every 2/4 weeks with 15% savings).\n"
                "- SOCIAL PROOF: Implement an authentic verified customer reviews carousel with star ratings and photo badges.\n"
                "- TRANSPARENCY: Display origin sourcing details, flavor notes matrix, and free shipping guarantee pills."
            )

        if any(w in ind or w in cat for w in ("architect", "real estate", "interior", "property", "luxury")):
            return (
                "- LUXURY EDITORIAL LAYOUT: Use generous whitespace, full-bleed high-resolution architectural project photography, and sophisticated serif/sans pairings.\n"
                "- PROJECT PORTFOLIO: Implement an interactive project gallery with filterable categories (Residential, Commercial, Civic).\n"
                "- BEFORE & AFTER / INTERACTIVE: Feature before-and-after renovation sliders and interactive floorplan hotspots.\n"
                "- CONSULTATION: Incorporate a discreet, high-touch consultation scheduler for high-net-worth clients."
            )

        if any(w in ind or w in cat for w in ("contractor", "construction", "trade", "plumb", "electric", "roof")):
            return (
                "- TRUST & LICENSING: Emphasize Licensed, Bonded & Insured guarantee badge and local operating licenses.\n"
                "- INSTANT ESTIMATE: Build a quick project estimate calculator tool with instant quote request.\n"
                "- PROOF OF WORK: Showcase before/after project transformation cards with material breakdowns and completion timelines.\n"
                "- EMERGENCY HOTLINE: Feature a click-to-call 24/7 dispatch hotline button in the sticky top header."
            )

        # Default modern B2B SaaS / Professional Services
        return (
            "- SOCIAL PROOF: Include trusted client logo marquee, G2/Capterra badges, and verified ROI case studies.\n"
            "- PRODUCT PREVIEW: Feature an interactive feature walkthrough with animated UI preview tabs.\n"
            "- CONVERSION: Provide dual CTAs ('Start Free Trial' and 'Schedule Demo') across the hero and sticky navigation."
        )

