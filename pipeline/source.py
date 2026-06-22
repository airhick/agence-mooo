"""CSV source: normalize scraped rows into clean Business records."""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from . import config


# Lowercase TLD only -> naturally trims glued trailing junk like "...comSUIVRE".
_EMAIL_RE = re.compile(r"[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[a-z]{2,24}")
# Known business inbox prefixes, preferred first when ordering candidates.
_PREFERRED = ("contact", "info", "hello", "bonjour", "accueil", "reservation",
              "reservations", "direction", "commercial", "rh")
# Template placeholders the scraper picks up from un-filled site boilerplate.
_PLACEHOLDER_DOMAINS = {"example.com", "yourdomain.com", "domain.com", "email.com",
                        "votredomaine.com", "monsite.com", "sitename.com"}
_PLACEHOLDER_LOCALS = {"youremail", "votreemail", "nom", "name", "yourname",
                       "prenom", "prenom.nom", "email", "exemple", "example"}


def _clean_local(local: str) -> str:
    """Strip a glued leading numeric run the scraper prepends (e.g. '72contact',
    '05info', '99collectionballeron' -> 'contact'/'info'/'collectionballeron')."""
    return re.sub(r"^\d+", "", local)


def _clean(value: str | None) -> str:
    """Strip the layered quoting the scraper produced (e.g. '\"\"\"foo\"\"\"')."""
    if not value:
        return ""
    v = value.strip()
    # Collapse repeated double-quotes then trim a single surrounding pair.
    v = v.replace('"""', '"').strip('"').strip()
    return "" if v in {'', '""'} else v


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text or "site"


@dataclass
class Business:
    name: str
    place_id: str
    address: str
    industry: str            # cleaned, comma-joined tags
    rating: str
    reviews: str
    phone: str
    intl_phone: str
    website: str
    email: str
    lat_long: str
    plus_code: str
    status: str = ""          # value of the CSV mooo_status column (empty = not processed)
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def emails(self) -> list[str]:
        """All distinct, deliverable contact addresses from the scraped field,
        best first. Used both as the qualify gate (must be non-empty) and as the
        set of email recipients (every business inbox is addressed).

        The scraper is noisy: it glues junk onto addresses and repeats corrupted
        copies of the same inbox. We clean that so we address the *real* inboxes,
        not bounce-bound artifacts:
          - the lowercase-TLD regex drops trailing garbage ('...frOuvert');
          - a glued leading numeric run is stripped ('72contact' -> 'contact'),
            which also collapses '72/82/45contact@x' down to one address;
          - on a shared domain, a longer local that ends with a shorter one AND
            carries a capitalised/numeric glued prefix is dropped as a corrupted
            copy ('XVIcontact'/'Parisinfo' when 'contact'/'info' is present);
          - obvious template placeholders ('nom@mail.com', 'youremail@...') drop.
        Genuinely distinct inboxes ('contact@x' + 'getacooljob@x') are all kept.
        """
        seen: dict[str, str] = {}   # "local@domain" (lowercased) -> display form
        for m in _EMAIL_RE.findall(self.email or ""):
            local, _, domain = m.partition("@")
            local = _clean_local(local)
            domain = domain.lower()
            if not local or domain in _PLACEHOLDER_DOMAINS \
                    or local.lower() in _PLACEHOLDER_LOCALS:
                continue
            seen.setdefault(f"{local.lower()}@{domain}", f"{local}@{domain}")

        # Drop corrupted copies: same domain, longer local ending with a shorter
        # one via a capitalised/numeric glued prefix (e.g. 'XVIcontact'/'Parisinfo').
        addrs = list(seen.values())
        drop: set[str] = set()
        for a in addrs:
            al, ad = a.lower().split("@")
            for b in addrs:
                if b is a:
                    continue
                bl, bd = b.lower().split("@")
                if bd == ad and len(bl) > len(al) and bl.endswith(al):
                    prefix = b.split("@")[0][: len(bl) - len(al)]
                    if any(c.isupper() or c.isdigit() for c in prefix):
                        drop.add(b)
        cands = [a for a in addrs if a not in drop]
        cands.sort(key=lambda e: (e.split("@")[0].lower() not in _PREFERRED,
                                  len(e.split("@")[0])))
        return cands

    @property
    def has_website(self) -> bool:
        return bool(self.website) and self.website.lower() not in {"n/a", "none"}

    @property
    def reviews_count(self) -> int:
        """Reviews as an int, tolerant of '1 234', '1,234', '1.2k' style scraping."""
        digits = re.sub(r"[^\d]", "", self.reviews or "")
        return int(digits) if digits else 0

    @property
    def status_key(self) -> str:
        """Stable key used to dedupe in the CSV (Place ID, else name|address)."""
        return self.place_id or f"{self.name}|{self.address}"

    @property
    def is_processed(self) -> bool:
        """Only a finished lead (done/error) is skipped on the next run.

        A `skipped:` stamp is NOT final: it just records why a lead failed the
        last target's gate, and must stay re-checkable so the same lead can still
        qualify under a different --target (e.g. a no-website lead skipped by a
        has-site run still qualifies for a no-site run)."""
        s = self.status.strip()
        return s.startswith("done") or s.startswith("error")

    @property
    def slug(self) -> str:
        s = slugify(self.name)
        if s in config.RESERVED_SLUGS:
            s = f"{s}-biz"
        return s

    @property
    def maps_query(self) -> str:
        return self.place_id or f"{self.name} {self.address}"


def resolve_unique_dir(base: Path, slug: str, place_id: str) -> Path:
    """Return a stable per-business folder under `base`.

    Reuses the same folder for the same business (matched by place_id in its
    meta.json) so re-runs update in place; otherwise picks a free `slug`,
    `slug-2`, `slug-3`... so two different businesses never collide.
    """
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / slug
    n = 1
    while True:
        if not candidate.exists():
            return candidate
        meta = candidate / "meta.json"
        if meta.exists():
            try:
                if json.loads(meta.read_text(encoding="utf-8")).get("place_id") == place_id and place_id:
                    return candidate  # same business -> update in place
            except (json.JSONDecodeError, OSError):
                pass
        n += 1
        candidate = base / f"{slug}-{n}"


def _industry_tags(raw: str) -> str:
    tags = [t.strip() for t in (raw or "").splitlines() if t.strip()]
    return ", ".join(tags)


def read_rows(csv_path: Path | None = None) -> Iterator[Business]:
    path = csv_path or config.CSV_PATH
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = _clean(row.get("Name"))
            if not name:
                continue
            yield Business(
                name=name,
                place_id=_clean(row.get("Place ID")),
                address=_clean(row.get("Adress")),
                industry=_industry_tags(row.get("Industry", "")),
                rating=_clean(row.get("Rating")).replace(",", "."),
                reviews=_clean(row.get("Number of reviews")),
                phone=_clean(row.get("Phone number")),
                intl_phone=_clean(row.get("International Phone number")),
                website=_clean(row.get("website")),
                email=_clean(row.get("scraped_emails")),
                lat_long=_clean(row.get("Lat - Long")),
                plus_code=_clean(row.get("Compound code")),
                status=_clean(row.get(config.CSV_STATUS_COL)),
                raw=row,
            )


# --------------------------------------------------------------------------- #
# CSV write-back: mark processed leads so they are never targeted twice.
# --------------------------------------------------------------------------- #
def _row_key(row: dict) -> str:
    """Mirror of Business.status_key, computed straight from a raw CSV row."""
    place_id = _clean(row.get("Place ID"))
    return place_id or f"{_clean(row.get('Name'))}|{_clean(row.get('Adress'))}"


def write_statuses(updates: dict[str, dict], csv_path: Path | None = None) -> int:
    """Rewrite the source CSV, stamping status columns on the updated leads.

    `updates` maps a Business.status_key to a dict with any of
    `mooo_status` / `mooo_url` / `mooo_at`. The whole CSV is rewritten once
    (atomic temp-file swap), so this is called a single time at the end of a run.
    Returns the number of rows updated.
    """
    if not updates:
        return 0
    path = csv_path or config.CSV_PATH
    extra = [config.CSV_STATUS_COL, config.CSV_URL_COL, config.CSV_AT_COL]
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(path, newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or [])
        for col in extra:
            if col not in fields:
                fields.append(col)
        with open(tmp, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in reader:
                upd = updates.get(_row_key(row))
                if upd:
                    row.update({k: v for k, v in upd.items() if k in extra})
                    n += 1
                writer.writerow(row)
    os.replace(tmp, path)
    return n
