"""Curated, verified imagery + font pairings so DeepSeek builds premium sites
with REAL working photos instead of hallucinated/broken image URLs.

All Unsplash IDs below were verified to return HTTP 200 from images.unsplash.com.
Each entry carries a short subject hint so the model writes sensible alt text
and places images coherently.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

U = "https://images.unsplash.com/{id}?w={w}&q=80&auto=format&fit=crop"


def img(photo_id: str, w: int = 1600) -> str:
    return U.format(id=photo_id, w=w)


# subject hint -> photo id, grouped by business category.
CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "restaurant": [
        ("salle de restaurant chaleureuse", "photo-1517248135467-4c7edcad34c4"),
        ("table dressée gastronomique", "photo-1414235077428-338989a2e8c0"),
        ("assiette gastronomique dressée", "photo-1559339352-11d035aa65de"),
        ("intérieur de restaurant moderne", "photo-1552566626-52f8b828add9"),
        ("plats partagés vue de dessus", "photo-1442512595331-e89e73853f31"),
        ("cuisine en préparation", "photo-1504674900247-0877df9cc836"),
        ("table dîner conviviale", "photo-1528605248644-14dd04022da1"),
    ],
    "cafe": [
        ("tasse de café latte art", "photo-1466978913421-dad2ebd01d17"),
        ("intérieur de café cosy", "photo-1554118811-1e0d58224f24"),
        ("barista et grains de café", "photo-1495474472287-4d71bcdd2085"),
        ("café servi en terrasse", "photo-1509042239860-f550ce710b93"),
        ("café avec plantes lumineux", "photo-1521017432531-fbd92d768814"),
        ("comptoir de coffee shop", "photo-1555396273-367ea4eb4db5"),
    ],
    "bar": [
        ("cocktails colorés au bar", "photo-1470337458703-46ad1756a187"),
        ("ambiance tamisée de bar", "photo-1543007630-9710e4a00a20"),
        ("cocktail signature", "photo-1481833761820-0509d3217039"),
        ("verres et vin au comptoir", "photo-1453614512568-c4024d13c247"),
    ],
    "bakery": [
        ("viennoiseries et croissants", "photo-1517433670267-08bbd4be890f"),
        ("pains frais artisanaux", "photo-1559925393-8be0ec4767c8"),
        ("miches de pain dorées", "photo-1559054663-e8d23213f55c"),
    ],
    "food": [  # generic food / takeaway / fast food
        ("burger gourmand", "photo-1572116469696-31de0f17cc34"),
        ("pizza artisanale", "photo-1513104890138-7c749659a591"),
        ("burger maison", "photo-1551782450-a2132b4ba21d"),
        ("plats partagés vue de dessus", "photo-1442512595331-e89e73853f31"),
    ],
    "store": [  # retail / shop / convenience
        ("devanture de boutique", "photo-1441986300917-64674bd600d8"),
        ("rayons de magasin soignés", "photo-1556742049-0cfed4f6a45d"),
        ("produits en vitrine", "photo-1604719312566-8912e9227c6a"),
        ("intérieur de boutique design", "photo-1560066984-138dadb4c035"),
    ],
    "generic": [  # services, beauty, health, default
        ("commerce de quartier accueillant", "photo-1487058792275-0ad4aaf24ca7"),
        ("espace intérieur élégant", "photo-1497366216548-37526070297c"),
        ("détail de matière et lumière", "photo-1521590832167-7bcbfaa6381f"),
        ("accueil chaleureux", "photo-1600880292203-757bb62b4baf"),
    ],
}

# Order matters: first matching tag wins.
TAG_TO_CATEGORY = [
    ("bakery", "bakery"), ("boulang", "bakery"), ("patiss", "bakery"),
    ("cafe", "cafe"), ("coffee", "cafe"),
    ("bar", "bar"), ("pub", "bar"), ("night_club", "bar"), ("liquor", "bar"),
    ("restaurant", "restaurant"),
    ("meal", "food"), ("food", "food"), ("takeaway", "food"),
    ("store", "store"), ("shop", "store"), ("supermarket", "store"),
    ("grocery", "store"), ("convenience", "store"), ("market", "store"),
]

# Distinctive Google Font pairings (display, body). Chosen per business so sites
# don't converge on the same look. NEVER the generic Inter/Roboto/Arial default.
FONT_PAIRS = [
    ("Fraunces", "Manrope"),
    ("Playfair Display", "Source Sans 3"),
    ("Cormorant Garamond", "Jost"),
    ("Syne", "Outfit"),
    ("DM Serif Display", "DM Sans"),
    ("Libre Baskerville", "Karla"),
    ("Marcellus", "Mulish"),
    ("Bricolage Grotesque", "Hanken Grotesk"),
    ("Unbounded", "Albert Sans"),
    ("Instrument Serif", "Geist"),
]


@dataclass
class AssetKit:
    category: str
    hero: str            # full url
    hero_hint: str
    gallery: list[dict]  # [{url, hint}]
    display_font: str
    body_font: str

    def fonts_css_url(self) -> str:
        def fam(name: str) -> str:
            return name.replace(" ", "+")
        return (
            "https://fonts.googleapis.com/css2?"
            f"family={fam(self.display_font)}:wght@400;500;600;700"
            f"&family={fam(self.body_font)}:wght@300;400;500;600;700&display=swap"
        )


def _category_for(industry: str) -> str:
    tags = industry.lower()
    for needle, cat in TAG_TO_CATEGORY:
        if needle in tags:
            return cat
    return "generic"


def _stable_index(seed: str, n: int) -> int:
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return h % max(n, 1)


def pick(name: str, industry: str) -> AssetKit:
    """Deterministically pick a coherent image set + font pairing for a business."""
    cat = _category_for(industry)
    pool = CATEGORIES.get(cat, CATEGORIES["generic"])
    # Rotate the pool by a per-business offset so neighbours differ.
    off = _stable_index(name, len(pool))
    rotated = pool[off:] + pool[:off]
    hero_hint, hero_id = rotated[0]
    gallery = [{"url": img(pid, 1200), "hint": hint} for hint, pid in rotated[1:6]]
    fp = FONT_PAIRS[_stable_index(name + cat, len(FONT_PAIRS))]
    return AssetKit(
        category=cat,
        hero=img(hero_id, 1920),
        hero_hint=hero_hint,
        gallery=gallery,
        display_font=fp[0],
        body_font=fp[1],
    )
