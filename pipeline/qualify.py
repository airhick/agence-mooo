"""Lead qualification gate (step 1 of the outreach funnel).

A business is worth the full pipeline only if it is an established, reachable
local business with a contact email AND an existing website — the outreach email
literally pitches "we saw your website and built you a new one", so a site must
already exist.

Criteria:
- more than REVIEWS_MIN (default 100) Google reviews;
- an active Google page (we proxy this with a present Place ID — the row came
  from a live Maps listing — plus a rating);
- at least one scraped contact email;
- an existing website.
"""
from __future__ import annotations

from . import config
from .source import Business


def qualify(biz: Business) -> tuple[bool, str]:
    """Return (ok, reason). `reason` explains a rejection for the CSV log."""
    if biz.reviews_count <= config.REVIEWS_MIN:
        return False, f"reviews {biz.reviews_count} <= {config.REVIEWS_MIN}"
    if not biz.place_id:
        return False, "no Google Place ID (inactive/unknown listing)"
    if not biz.rating:
        return False, "no Google rating"
    if not biz.email:
        return False, "no contact email"
    if not biz.has_website:
        return False, "no existing website"
    return True, "qualified"
