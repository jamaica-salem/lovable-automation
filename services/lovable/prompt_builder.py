"""Prompt builder for Lovable website redesign generation."""

import base64
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings
from prompts.reference_rules import REFERENCE_RULES_DIRECTIVE
from services.website_analysis.models import WebsiteAnalysis
from utils.logger import logger


class LovablePromptBuilder:
    """Constructs production-grade redesign prompts for Lovable.
    
    Guarantees that the design reference provides layout and structural inspiration
    while strictly preserving the original website's content, branding, and identity.
    """

    async def build_redesign_prompt_async(
        self,
        website_url: str,
        business_name: Optional[str] = None,
        analysis: Optional[WebsiteAnalysis] = None,
        design_reference: Optional[Dict[str, Any]] = None,
        additional_instructions: Optional[str] = None,
    ) -> str:
        """Asynchronously build redesign prompt, utilizing Gemini Multimodal Vision if configured with heuristic fallback."""
        heuristic_prompt = self.build_redesign_prompt(
            website_url=website_url,
            business_name=business_name,
            analysis=analysis,
            design_reference=design_reference,
            additional_instructions=additional_instructions,
        )

        if not settings.gemini_api_key:
            return heuristic_prompt

        b_name = business_name or (analysis.business_name if analysis else None) or "Target Business"
        industry = (analysis.industry if analysis else None) or "Technology & Services"
        target_audience = (analysis.target_audience if analysis else None) or "B2B"

        ref = design_reference or {}
        ref_title = ref.get("title") or ref.get("design_reference_title") or "Modern Aesthetic UI"
        ref_url = ref.get("url") or ref.get("design_reference_url") or "https://dribbble.com"
        ref_image = ref.get("image_url") or ref.get("design_reference_image") or ""
        ref_tags = ref.get("tags") or []
        ref_palette = ref.get("color_palette") or []

        ref_info_lines = [
            f"- Title: {ref_title}",
            f"- URL: {ref_url}",
        ]
        if ref_image:
            ref_info_lines.append(f"- Preview Image: {ref_image}")
        if ref_tags:
            ref_info_lines.append(f"- Aesthetic Tags: {', '.join(ref_tags)}")
        if ref_palette:
            ref_info_lines.append(f"- Reference Accents: {', '.join(ref_palette)}")
        ref_info = "\n".join(ref_info_lines)

        system_instruction = (
            "You are a world-class Principal UI/UX Architect and Lovable Prompt Engineer. "
            "Your job is to generate an exceptional, highly specific, production-grade redesign prompt for Lovable.\n"
            "Strict Guidelines:\n"
            "1. BRAND PRESERVATION: Strictly preserve the target company's real brand identity, name, and color palette.\n"
            "2. MULTIMODAL VISION ARCHITECTURE: If a design reference screenshot image is attached, inspect the image visually: examine its exact layout structure, bento grids, split-screen hero framing, card elevations, container padding, whitespace pacing, navigation style, typography hierarchy, and micro-interactions. "
            f"You MUST include a dedicated section titled '## 🎨 Dribbble Layout & Visual Reference ({ref_title})' explaining exactly how to translate "
            "the visual patterns seen in this screenshot image into Lovable React/Tailwind components without copying its placeholder company name or copy.\n"
            "3. MODERNITY: Include dark/light mode surface styling, glassmorphism cards, modern typography (Inter/Outfit), fluid responsive layout, and domain-specific conversion widgets.\n"
            "4. CLIENT DIRECTIVES: Prominently feature all client custom requirements and notes.\n"
            "Output clean, complete markdown formatted as a prompt ready for Lovable."
        )

        user_content = (
            f"# REDESIGN SPECIFICATION REQUEST\n"
            f"Business Name: {b_name}\n"
            f"Original URL: {website_url}\n"
            f"Industry / Category: {industry}\n"
            f"Target Audience: {target_audience}\n\n"
            f"Selected Dribbble Design Reference:\n{ref_info}\n\n"
            f"Client Notes: {additional_instructions or 'None'}\n\n"
            f"Baseline Architectural Context:\n{heuristic_prompt}\n\n"
            "Please expand and refine this prompt into an exceptional, creative, and specific redesign prompt for Lovable that explicitly bases its layout and UI architecture on the Dribbble design reference."
        )

        # Attempt to download reference screenshot image for Gemini Vision analysis
        image_part = None
        if ref_image:
            try:
                async with httpx.AsyncClient(timeout=8.0) as img_client:
                    img_resp = await img_client.get(ref_image)
                    if img_resp.status_code == 200 and img_resp.content:
                        mime_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                        if mime_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                            mime_type = "image/jpeg"
                        b64_data = base64.b64encode(img_resp.content).decode("utf-8")
                        image_part = {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_data,
                            }
                        }
                        logger.info(f"Loaded design screenshot for Gemini Vision analysis ({len(img_resp.content)} bytes)")
            except Exception as img_err:
                logger.warning(f"Could not load design image for vision analysis: {img_err}")

        # Assemble multimodal content parts
        parts = []
        if image_part:
            parts.append(image_part)
            vision_note = (
                f"\n\n[ATTACHED DESIGN REFERENCE SCREENSHOT: {ref_title}]\n"
                "Carefully inspect the visual layout, card borders, elevation, header, spacing, and grid architecture in the attached design screenshot. "
                f"Extract its visual design language to build the redesign prompt for {b_name}."
            )
            parts.append({"text": user_content + vision_note})
        else:
            parts.append({"text": user_content})

        url = f"https://generativelanguage.googleapis.com/v1beta/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        payload = {
            "contents": [{"parts": parts}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        resp_parts = candidates[0].get("content", {}).get("parts", [])
                        if resp_parts and resp_parts[0].get("text"):
                            logger.info(f"Successfully generated AI redesign prompt via Gemini Vision ({settings.gemini_model})")
                            return resp_parts[0]["text"].strip()
                logger.warning(f"Gemini API returned status {res.status_code}: {res.text[:150]}. Using heuristic prompt.")
        except Exception as exc:
            logger.warning(f"Gemini prompt generation failed or timed out: {exc}. Using heuristic prompt.")

        return heuristic_prompt


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

