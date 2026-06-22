"""Company research (step 2): gather real facts + imagery to feed the AI.

Three best-effort sources, each wrapped so a failure never breaks the funnel:
  1. The business's OWN website  — via `fetcher.fetch` (title, headings, copy).
  2. The wider web              — a keyless DuckDuckGo HTML search for context.
  3. Its Google Maps place page — via headless Playwright: description, category,
     and real photos of the business, which are downloaded locally so they
     persist and deploy with the site.

Returns a `Research` object whose `.context()` is injected into the audit and
build prompts, and whose `.local_images` are real photos the generator places on
the site (falling back to curated stock in `assets.py` when none were found).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from . import config
from .fetcher import PageContent, fetch
from .source import Business

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_IMAGES = 6


@dataclass
class Research:
    own_site: PageContent | None = None
    web_snippets: list[str] = field(default_factory=list)
    maps_text: str = ""
    local_images: list[dict] = field(default_factory=list)  # [{path, hint}] (paths relative to site dir)
    notes: list[str] = field(default_factory=list)          # what worked / what was skipped

    @property
    def has_real_images(self) -> bool:
        return bool(self.local_images)

    def context(self) -> str:
        """Compact markdown block of everything found, for the LLM prompts."""
        parts: list[str] = []
        if self.own_site and self.own_site.ok:
            s = self.own_site
            parts.append(
                "### Site actuel\n"
                f"- Titre: {s.title or '—'}\n"
                f"- Description: {s.meta_description or '—'}\n"
                f"- H1: {' | '.join(s.h1) or '—'}\n"
                f"- H2: {' | '.join(s.h2[:8]) or '—'}\n"
                f"- Extrait: {(s.text or '')[:1500]}"
            )
        if self.maps_text:
            parts.append("### Fiche Google Maps\n" + self.maps_text[:1500])
        if self.web_snippets:
            parts.append("### Mentions web\n" + "\n".join(
                f"- {sn}" for sn in self.web_snippets[:6]))
        return "\n\n".join(parts) if parts else "(aucune information complémentaire trouvée)"


# --------------------------------------------------------------------------- #
# Source 2 — keyless web search (DuckDuckGo HTML endpoint)
# --------------------------------------------------------------------------- #
def _web_search(query: str) -> list[str]:
    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query}, headers={"User-Agent": UA},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out: list[str] = []
        for res in soup.select(".result__body")[:6]:
            title = res.select_one(".result__title")
            snippet = res.select_one(".result__snippet")
            line = " ".join(
                x.get_text(" ", strip=True)
                for x in (title, snippet) if x
            ).strip()
            if line:
                out.append(re.sub(r"\s+", " ", line)[:240])
        return out
    except requests.RequestException:
        return []


# --------------------------------------------------------------------------- #
# Source 3 — Google Maps place page via headless Playwright (optional)
# --------------------------------------------------------------------------- #
def _download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=config.HTTP_TIMEOUT)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def _maps(biz: Business, assets_dir: Path | None) -> tuple[str, list[dict]]:
    """Return (maps_text, [{path, hint}]) — empty on any failure."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", []

    place = (f"https://www.google.com/maps/place/?q=place_id:{biz.place_id}"
             if biz.place_id else
             f"https://www.google.com/maps/search/{quote_plus(biz.name + ' ' + biz.address)}")
    text, image_urls = "", []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="fr-FR")
            page.goto(place, wait_until="domcontentloaded", timeout=30000)
            # Dismiss the EU consent wall if present.
            for sel in ('button[aria-label*="Tout accepter"]',
                        'button[aria-label*="Accept all"]',
                        'form[action*="consent"] button'):
                try:
                    page.click(sel, timeout=2500)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(3500)
            text = re.sub(r"\s+", " ", page.inner_text("body"))[:2000]
            srcs = page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src).filter(s => s && s.includes('googleusercontent'))",
            )
            seen: set[str] = set()
            for s in srcs:
                base = s.split("=")[0]
                if base in seen:
                    continue
                seen.add(base)
                image_urls.append(s.split("=")[0] + "=w1600")  # request a large variant
                if len(image_urls) >= MAX_IMAGES:
                    break
            browser.close()
    except Exception:  # noqa: BLE001 - scraping is inherently flaky; degrade gracefully
        return text, []

    images: list[dict] = []
    if assets_dir and image_urls:
        assets_dir.mkdir(parents=True, exist_ok=True)
        for i, url in enumerate(image_urls, 1):
            dest = assets_dir / f"maps-{i}.jpg"
            if _download(url, dest):
                images.append({"path": f"assets/{dest.name}",
                               "hint": f"photo réelle du commerce ({i})"})
    return text, images


# --------------------------------------------------------------------------- #
def research(biz: Business, assets_dir: Path | None = None) -> Research:
    r = Research()

    if biz.has_website:
        r.own_site = fetch(biz.website)
        r.notes.append("site:" + ("ok" if r.own_site and r.own_site.ok else "ko"))

    city = biz.address.split(",")[-1].strip() if biz.address else ""
    r.web_snippets = _web_search(f"{biz.name} {city}".strip())
    r.notes.append(f"web:{len(r.web_snippets)}")

    r.maps_text, r.local_images = _maps(biz, assets_dir)
    r.notes.append(f"maps:{len(r.local_images)}img")

    return r
