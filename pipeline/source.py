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
        return bool(self.status.strip())

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
