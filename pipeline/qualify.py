"""Lead qualification gate (step 1 of the outreach funnel).

Both targets require an active Google page (proxied by a present Place ID +
rating), at least one scraped contact email, and at least REVIEWS_MIN (default
50) reviews. They differ only by website presence:

- target "has-site" (default): it ALREADY has a website -> the email pitches a
  redesign ("we saw your site and built you a new one").
- target "no-site": it has NO website -> the email pitches a first site ("you
  had no site, so we made you one").
"""
from __future__ import annotations

from . import config
from .source import Business


def qualify(biz: Business, target: str = config.DEFAULT_TARGET) -> tuple[bool, str]:
    """Return (ok, reason). `reason` explains a rejection for the CSV log."""
    spec = config.TARGETS[target]
    if not biz.place_id:
        return False, "no Google Place ID (inactive/unknown listing)"
    if not biz.rating:
        return False, "no Google rating"
    if not biz.email:
        return False, "no contact email"
    if biz.reviews_count < spec["reviews_min"]:
        return False, f"reviews {biz.reviews_count} < {spec['reviews_min']}"
    if spec["needs_website"] and not biz.has_website:
        return False, "no existing website"
    if not spec["needs_website"] and biz.has_website:
        return False, "already has a website"
    return True, "qualified"
