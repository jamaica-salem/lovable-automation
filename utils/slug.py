"""Deterministic slug generation with collision handling."""

import re
import unicodedata
from typing import Optional, Set
from urllib.parse import urlparse


def clean_name(text: str) -> str:
    """Normalize text by converting unicode, replacing symbols, and removing punctuation."""
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Lowercase
    text = text.lower()
    # Remove apostrophes and quotes for clean possessives and contractions
    text = text.replace("'", "").replace("’", "").replace('"', "").replace("`", "")
    # Replace common symbols
    text = text.replace("&", " and ").replace("@", " at ")
    # Replace any non-alphanumeric characters with a hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    return text.strip("-")


def extract_domain_name(url: str) -> str:
    """Extract a clean base domain name from a URL."""
    if not url:
        return "website"
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path
        # Remove www and port
        host = re.sub(r"^www\.", "", host)
        host = host.split(":")[0]
        # Get first segment of domain
        parts = host.split(".")
        if len(parts) >= 2:
            return parts[0]
        return host
    except Exception:
        return "website"


def generate_slug(
    business_name: Optional[str] = None,
    website_url: Optional[str] = None,
    existing_slugs: Optional[Set[str]] = None,
    suffix: str = "modern",
    max_name_length: int = 40,
) -> str:
    """Generate a deterministic, URL-safe slug with collision handling.
    
    Examples:
        "NYC Petcare" -> "nyc-petcare-modern"
        "Happy Paws Veterinary" -> "happy-paws-veterinary-modern"
        "Austin Dental Clinic" -> "austin-dental-clinic-modern"
    """
    raw_name = (business_name or "").strip()
    if not raw_name:
        raw_name = extract_domain_name(website_url or "")

    cleaned = clean_name(raw_name)
    if not cleaned:
        cleaned = "site"

    # Truncate to maximum name length if needed
    if len(cleaned) > max_name_length:
        cleaned = cleaned[:max_name_length].rstrip("-")

    base_slug = f"{cleaned}-{suffix}" if suffix else cleaned

    if existing_slugs is None:
        return base_slug

    # Collision resolution: append deterministic suffix -2, -3, ...
    if base_slug not in existing_slugs:
        return base_slug

    counter = 2
    while True:
        candidate = f"{base_slug}-{counter}"
        if candidate not in existing_slugs:
            return candidate
        counter += 1
