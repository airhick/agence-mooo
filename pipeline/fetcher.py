"""Fetch and extract structured content from an existing website for auditing."""
from __future__ import annotations

from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from . import config

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class PageContent:
    ok: bool
    url: str
    final_url: str = ""
    status: int = 0
    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    text: str = ""
    n_images: int = 0
    n_links: int = 0
    has_viewport: bool = False
    has_favicon: bool = False
    lang: str = ""
    error: str = ""


def fetch(url: str, timeout: int | None = None) -> PageContent:
    timeout = timeout or config.HTTP_TIMEOUT
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True
        )
    except requests.RequestException as exc:
        return PageContent(ok=False, url=url, error=str(exc)[:300])

    if resp.status_code >= 400:
        return PageContent(
            ok=False, url=url, final_url=resp.url, status=resp.status_code,
            error=f"HTTP {resp.status_code}",
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    def meta(name: str, attr: str = "name") -> str:
        el = soup.find("meta", attrs={attr: name})
        return (el.get("content") or "").strip() if el else ""

    text = " ".join(soup.get_text(" ").split())
    return PageContent(
        ok=True,
        url=url,
        final_url=resp.url,
        status=resp.status_code,
        title=(soup.title.string or "").strip() if soup.title else "",
        meta_description=meta("description") or meta("og:description", "property"),
        h1=[h.get_text(" ", strip=True) for h in soup.find_all("h1")][:10],
        h2=[h.get_text(" ", strip=True) for h in soup.find_all("h2")][:15],
        text=text[:6000],
        n_images=len(soup.find_all("img")),
        n_links=len(soup.find_all("a")),
        has_viewport=bool(soup.find("meta", attrs={"name": "viewport"})),
        has_favicon=bool(soup.find("link", rel=lambda v: v and "icon" in v)),
        lang=(soup.html.get("lang", "") if soup.html else ""),
    )
