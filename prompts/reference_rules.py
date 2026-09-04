"""Design reference utilization rules and prompt constraints.

Enforces strict boundaries between design inspiration and brand identity.
"""

REFERENCE_RULES_DIRECTIVE = """
CRITICAL DESIGN REFERENCE GUIDELINES:
1. LAYOUT & HIERARCHY ONLY: The selected design reference is provided strictly for visual layout, section hierarchy, whitespace pacing, modern component styling, and aesthetic inspiration.
2. PRESERVE ORIGINAL IDENTITY: NEVER copy the reference company's branding, logos, trademark names, product titles, or specific imagery.
3. PRESERVE ORIGINAL CONTENT & VALUE PROPOSITION: All text copy, business details, service descriptions, contact information, and core offerings from the original website MUST remain authoritative and intact.
4. BRAND PALETTE REFINEMENT: Use the original website's brand colors as the primary baseline. The reference palette may only be used for complementary accents, neutral dark/light surfaces, and modern contrast elevation.
5. NO PLACEHOLDERS: Generate complete, functional UI elements with realistic typography, semantic HTML, and responsive CSS rather than dummy placeholders.
""".strip()


def format_reference_directive(reference_title: str, reference_source: str = "dribbble") -> str:
    """Format structured reference prompt injection ensuring strict adherence to boundary rules."""
    return f"""
[DESIGN REFERENCE DIRECTIVE]
Reference Source: {reference_source.title()} - "{reference_title}"
{REFERENCE_RULES_DIRECTIVE}
""".strip()
