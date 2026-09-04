"""Tests for website analysis service, HTML parsing, and offline fallback."""

import pytest
from services.website_analysis.analyzer import HttpWebsiteAnalyzer
from services.website_analysis.models import WebsiteAnalysis


SAMPLE_SAAS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CloudPulse - AI Workflow Automation Platform</title>
    <meta name="description" content="Streamline enterprise engineering workflows with automated AI agents.">
    <style>
        :root { --brand: #6366F1; --accent: #10B981; --dark: #0F172A; }
        body { font-family: 'Inter', sans-serif; background: #0F172A; color: #F8FAFC; }
    </style>
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/features">Features</a>
            <a href="/pricing">Pricing</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    <main>
        <section id="hero" class="hero-section">
            <h1>Automate Software Delivery with Next-Gen AI Agents</h1>
            <p>CloudPulse empowers modern DevOps teams to ship faster with automated code reviews.</p>
            <a href="/signup" class="cta-button">Start Free Trial</a>
        </section>
        <section id="features" class="feature-grid">
            <h2>Built for High-Growth Tech Teams</h2>
            <div class="card"><h3>Continuous Synthesis</h3><p>Real-time updates.</p></div>
            <div class="card"><h3>Enterprise Security</h3><p>SOC2 compliant.</p></div>
        </section>
        <section id="pricing" class="pricing-plans">
            <h2>Predictable Pricing</h2>
            <div class="plan"><h3>Growth</h3><p>$49/mo</p></div>
        </section>
        <section id="testimonials">
            <h2>Trusted by Leaders</h2>
            <blockquote>CloudPulse changed how we ship.</blockquote>
        </section>
        <section id="contact">
            <form action="/api/lead" method="POST">
                <input type="email" placeholder="Work email" />
                <button type="submit">Book Demo</button>
            </form>
        </section>
    </main>
    <footer>
        <p>© 2026 CloudPulse Inc. All rights reserved.</p>
    </footer>
</body>
</html>
"""

SAMPLE_HEALTHCARE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Apex Dental Clinic - Comprehensive Family Dentistry</title>
    <meta name="description" content="Gentle and compassionate dental care for patients of all ages.">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <h1>Welcoming Smiles at Apex Dental</h1>
    <p>Experienced doctors offering cosmetic, pediatric, and restorative dental treatments.</p>
    <section id="services">
        <h2>Our Services</h2>
        <p>Cleanings, whitening, and implants.</p>
    </section>
    <form id="appointment-form">
        <input type="text" name="patient_name">
    </form>
</body>
</html>
"""


def test_parse_html_saas():
    analyzer = HttpWebsiteAnalyzer()
    analysis = analyzer.parse_html(SAMPLE_SAAS_HTML, "https://cloudpulse.io")

    assert analysis.url == "https://cloudpulse.io"
    assert "CloudPulse" in (analysis.business_name or "")
    assert analysis.industry == "Software & Technology"
    assert analysis.category == "SaaS Platform"
    assert analysis.target_audience == "B2B"
    assert analysis.mobile_responsive is True
    assert "hero" in analysis.key_sections
    assert "features" in analysis.key_sections
    assert "pricing" in analysis.key_sections
    assert "contact" in analysis.key_sections
    assert "contact-lead-form" in analysis.functional_requirements
    assert analysis.offline_fallback is False
    assert len(analysis.detected_colors) >= 1
    assert len(analysis.suggested_improvements) >= 2


def test_parse_html_healthcare():
    analyzer = HttpWebsiteAnalyzer()
    analysis = analyzer.parse_html(SAMPLE_HEALTHCARE_HTML, "https://apexdental.com")

    assert analysis.industry == "Healthcare & Wellness"
    assert analysis.category == "Medical Clinic"
    assert analysis.target_audience == "B2C"
    assert analysis.mobile_responsive is True
    assert "Apex Dental Clinic" in (analysis.raw_title or "")


@pytest.mark.asyncio
async def test_offline_fallback_for_unreachable_site():
    analyzer = HttpWebsiteAnalyzer(timeout_seconds=0.5)
    # Using non-existent unreachable local domain
    analysis = await analyzer.analyze("https://non-existent-domain-xyz-123.internal")

    assert analysis.offline_fallback is True
    assert analysis.url == "https://non-existent-domain-xyz-123.internal"
    assert analysis.industry != ""
    assert analysis.category != ""
    assert len(analysis.key_sections) > 0
    assert len(analysis.suggested_improvements) > 0
    assert analysis.business_name == "Non Existent Domain Xyz 123"
