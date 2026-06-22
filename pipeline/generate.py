"""Premium single-page site generator (two-pass) for businesses without a site.

Pass A — Art direction: DeepSeek (reasoning) commits to a BOLD, context-specific
         aesthetic and writes a detailed French creative brief + real copy.
Pass B — Build: DeepSeek builds a production-grade page from the brief, using
         real curated photography, a distinctive Google Font pairing, motion and
         atmosphere — the kind of site a client would pay top dollar for.

Output: <slug>/index.html at repo root -> served at https://agence.mooo.com/<slug>.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote_plus

from . import assets, config, deepseek
from .gather import Research
from .source import Business, resolve_unique_dir

# --------------------------------------------------------------------------- #
# Pass A — Art direction
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = (
    "Tu es directeur de création dans un studio de design primé. Tu conçois des "
    "sites vitrine haut de gamme (budget 10 000 €+) pour des commerces locaux "
    "français. Avant d'écrire la moindre ligne de code, tu définis une DIRECTION "
    "ARTISTIQUE forte et singulière, jamais générique. Tu choisis un parti pris "
    "tranché (éditorial chic, minimal luxe, bistrot chaleureux, brut/industriel, "
    "art déco, organique/naturel, rétro-parisien...) cohérent avec l'activité, le "
    "quartier et la clientèle. Tu rédiges de vraies accroches en français, avec "
    "du caractère — pas de remplissage. Tu ne fabriques jamais de faux faits "
    "(prix précis, fausses citations clients, faux horaires)."
)

BRIEF_USER = """Conçois la direction artistique du site vitrine de ce commerce.

## Commerce (données réelles)
- Nom: {name}
- Activité (tags): {industry}
- Catégorie retenue: {category}
- Adresse: {address}  (quartier/ville à exploiter dans le ton)
- Note Google: {rating}/5 sur {reviews} avis
- Téléphone: {phone} | Email: {email}

## Police imposée (déjà choisie, à utiliser)
- Titres (display): {display_font}
- Texte courant (body): {body_font}

## Audit du site actuel (à corriger par la nouvelle DA)
{audit}

## Recherche réelle (web + Google Maps) à exploiter dans le contenu
{research}

## Livrable : un BRIEF CRÉATIF en français, structuré ainsi
1. **Concept & positionnement** (2-3 phrases : l'idée forte, ce qu'on retient).
2. **Direction artistique** : nomme le parti pris esthétique précis.
3. **Palette** : 4 à 6 couleurs en HEX avec rôle (fond, encre, accent, etc.).
   Palettes dominantes + accent franc ; bannis le « blanc fade + gris ».
   Choisis librement clair OU sombre selon ce qui sert l'ambiance.
4. **Ton éditorial** : voix, niveau de langue, registre.
5. **Accroche héro** : un grand titre percutant + sous-titre (vrai texte FR).
6. **Sections** : liste ordonnée des sections avec, pour chacune, le titre réel
   et une phrase de contenu réel (À propos, offre/carte, ambiance, infos, etc.).
7. **Signature visuelle** : 1-2 détails mémorables (traitement d'image, motif,
   typographie surdimensionnée, animation clé...) qui rendent le site unique.

Sois concret, spécifique à CE commerce. Pas de généralités interchangeables.
Réponds directement aux faiblesses pointées par l'audit ci-dessus."""


def _brief(biz: Business, kit: assets.AssetKit, audit_report: str | None,
           research: Research | None) -> str:
    prompt = BRIEF_USER.format(
        name=biz.name,
        industry=biz.industry or "commerce de proximité",
        category=kit.category,
        address=biz.address or "—",
        rating=biz.rating or "0",
        reviews=biz.reviews or "0",
        phone=biz.phone or biz.intl_phone or "—",
        email=biz.email or "—",
        display_font=kit.display_font,
        body_font=kit.body_font,
        audit=(audit_report or "(audit indisponible)")[:4000],
        research=research.context() if research else "(non collectée)",
    )
    return deepseek.chat(
        [{"role": "system", "content": BRIEF_SYSTEM},
         {"role": "user", "content": prompt}],
        model=config.GEN_MODEL, temperature=0.9, max_tokens=4000,
    )


# --------------------------------------------------------------------------- #
# Pass B — Build
# --------------------------------------------------------------------------- #
BUILD_SYSTEM = (
    "Tu es lead front-end designer. Tu transformes un brief créatif en UNE page "
    "HTML autonome, production-grade, du niveau d'un studio primé. Règles de "
    "qualité NON négociables :\n"
    "- Exécute le parti pris du brief avec précision et audace ; rien de "
    "générique. Jamais Inter/Roboto/Arial, jamais le cliché 'dégradé violet sur "
    "blanc'. Utilise les polices Google imposées.\n"
    "- Typographie expressive : grand display, vraie hiérarchie, interlignage et "
    "letter-spacing soignés, tailles fluides (clamp).\n"
    "- Composition : mise en page non triviale, asymétrie maîtrisée, "
    "chevauchements, grandes respirations OU densité contrôlée, grille qui se "
    "brise avec intention.\n"
    "- Atmosphère : profondeur via dégradés/mesh, grain/texture, ombres "
    "travaillées, filets décoratifs — pas d'aplats plats.\n"
    "- Mouvement : une orchestration d'entrée (reveals décalés au chargement) + "
    "apparitions au scroll (IntersectionObserver) + hover surprenants. CSS "
    "d'abord, JS vanilla minimal.\n"
    "- Images : utilise EXACTEMENT les URLs fournies (vraies photos), avec "
    "object-fit:cover, lazy-loading, et traitement cohérent avec la DA "
    "(duotone, overlay, grain...).\n"
    "- Responsive mobile-first impeccable, contrastes accessibles (AA), focus "
    "visibles, prefers-reduced-motion respecté.\n"
    "- Aucune donnée inventée : utilise les infos réelles, et pour ce qui manque "
    "(prix, horaires) reste neutre et honnête.\n"
    "Tu réponds avec le CODE HTML COMPLET et RIEN d'autre."
)

BUILD_USER = """Construis le site vitrine une page à partir de ce brief.

## BRIEF CRÉATIF (à exécuter fidèlement)
{brief}

## Données réelles du commerce
- Nom: {name}
- Activité: {industry}
- Adresse: {address}
- Téléphone: {phone}  (lien tel:{tel_raw})
- Email: {email}
- Note Google: {rating}/5 sur {reviews} avis
- URL de déploiement: {site_url}

## Polices Google (à charger via <link> dans le <head>)
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{fonts_url}" rel="stylesheet">
-> display: '{display_font}', body: '{body_font}'

## Images réelles à utiliser (NE PAS en inventer d'autres)
{image_note}
- HÉRO ({hero_hint}): {hero}
{gallery_block}

## Contraintes de contenu / techniques
- Langue: français. Sections fidèles au brief (héro, à propos, offre/carte,
  ambiance/galerie, avis, infos pratiques, contact).
- Header collant avec nom + nav ancre + CTA principal (Réserver / Appeler /
  Itinéraire selon l'activité).
- Mets en valeur la note Google {rating}★ ({reviews} avis) si > 0 (badge soigné).
- Infos pratiques : adresse, téléphone (tel:), email (mailto:), et un bloc
  horaires honnête ("Horaires à confirmer" si inconnu).
- Carte : intègre CET iframe exactement —
  <iframe src="{map_embed}" width="100%" height="360" style="border:0;"
   loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>
- Favicon inline (data URI SVG/emoji) via <link rel="icon"> pour éviter un 404.
- <title> + <meta name="description"> SEO local (nom + activité + ville),
  Open Graph (og:title, og:description, og:image = l'image héro).
- <script type="application/ld+json"> Schema.org LocalBusiness (name, address,
  telephone, aggregateRating {rating}/{reviews} si > 0, image = héro).
- Footer avec NAP complet + "Site créé par Agence Mooo".
Réponds uniquement avec le document HTML complet (commence par <!DOCTYPE html>)."""


def _maps_embed(biz: Business) -> str:
    q = quote_plus(f"{biz.name} {biz.address}".strip() or biz.name)
    return f"https://maps.google.com/maps?q={q}&output=embed"


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    m = re.search(r"<!DOCTYPE html|<html", t, re.IGNORECASE)
    return t[m.start():].strip() if m else t.strip()


def _images(kit: assets.AssetKit, research: Research | None) -> tuple[str, str, str, str]:
    """Pick imagery: real Google Maps photos first, curated stock as fallback.

    Returns (image_note, hero, hero_hint, gallery_block). Real photos are
    referenced by their relative path inside the site folder (e.g. assets/maps-1.jpg).
    """
    if research and research.has_real_images:
        imgs = research.local_images
        hero, hero_hint = imgs[0]["path"], imgs[0]["hint"]
        gallery_block = "\n".join(
            f"- GALERIE ({g['hint']}): {g['path']}" for g in imgs[1:]
        )
        note = ("Ce sont de VRAIES photos du commerce (chemins relatifs, déjà "
                "présentes dans le dossier du site). Utilise-les telles quelles.")
        return note, hero, hero_hint, gallery_block

    gallery_block = "\n".join(
        f"- GALERIE ({g['hint']}): {g['url']}" for g in kit.gallery
    )
    note = "Photos professionnelles soigneusement sélectionnées (URLs absolues vérifiées)."
    return note, kit.hero, kit.hero_hint, gallery_block


def _build(biz: Business, kit: assets.AssetKit, brief: str, eff_slug: str,
           research: Research | None) -> str:
    image_note, hero, hero_hint, gallery_block = _images(kit, research)
    prompt = BUILD_USER.format(
        brief=brief,
        name=biz.name,
        industry=biz.industry or "commerce de proximité",
        address=biz.address or "—",
        phone=biz.phone or biz.intl_phone or "—",
        email=biz.email or "—",
        rating=biz.rating or "0",
        reviews=biz.reviews or "0",
        site_url=f"{config.SITE_BASE_URL}/{eff_slug}",
        tel_raw=(biz.intl_phone or biz.phone or "").replace(" ", ""),
        fonts_url=kit.fonts_css_url(),
        display_font=kit.display_font,
        body_font=kit.body_font,
        image_note=image_note,
        hero=hero,
        hero_hint=hero_hint,
        gallery_block=gallery_block,
        map_embed=_maps_embed(biz),
    )
    html = deepseek.chat(
        [{"role": "system", "content": BUILD_SYSTEM},
         {"role": "user", "content": prompt}],
        model=config.GEN_MODEL, temperature=0.85, max_tokens=20000,
    )
    return _strip_fences(html)


def run_generate(biz: Business, audit_report: str | None = None,
                 research: Research | None = None, out_dir=None) -> dict:
    """Two-pass premium generation, chained from the audit + research.

    Writes <slug>/index.html + brief.md + meta.json. `out_dir` lets the caller
    reserve the folder first (so research can download real photos into it);
    when omitted it is resolved here.
    """
    kit = assets.pick(biz.name, biz.industry)
    # Reserve the per-business folder first so the URL matches the real folder.
    if out_dir is None:
        out_dir = resolve_unique_dir(config.SITES_DIR, biz.slug, biz.place_id)
    eff_slug = out_dir.name

    brief = _brief(biz, kit, audit_report, research)
    html = _build(biz, kit, brief, eff_slug, research)
    if "<html" not in html.lower():
        raise deepseek.DeepSeekError("Model did not return valid HTML")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "brief.md").write_text(brief, encoding="utf-8")

    site_url = f"{config.SITE_BASE_URL}/{eff_slug}"
    meta = {
        "name": biz.name, "slug": eff_slug, "place_id": biz.place_id,
        "type": "generate", "site_url": site_url, "model": config.GEN_MODEL,
        "category": kit.category, "fonts": f"{kit.display_font}/{kit.body_font}",
        "bytes": len(html.encode("utf-8")),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "output": str(out_dir / "index.html")}
