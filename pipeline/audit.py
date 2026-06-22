"""Audit an existing website with DeepSeek and write a markdown report."""
from __future__ import annotations

import json
from datetime import datetime

from . import config, deepseek
from .fetcher import PageContent, fetch
from .gather import Research
from .source import Business, resolve_unique_dir

AUDIT_SYSTEM = (
    "Tu es un consultant senior en conversion web et design UX/UI pour des "
    "commerces locaux français (restaurants, bars, cafés, boulangeries, "
    "commerces). Tu audites le site existant d'un commerce et tu rends un "
    "rapport actionnable, honnête et priorisé, en français. Tu te bases "
    "uniquement sur le contenu fourni (HTML/texte extrait) — tu ne vois pas "
    "les visuels, donc tu raisonnes sur la structure, le contenu, le parcours "
    "et les signaux techniques. Sois concret et spécifique au commerce."
)

AUDIT_TEMPLATE = """Voici un commerce et le contenu extrait de son site web actuel.

## Commerce
- Nom: {name}
- Activité: {industry}
- Adresse: {address}
- Note Google: {rating} ({reviews} avis)
- Téléphone: {phone}
- Email: {email}
- Site analysé: {final_url} (HTTP {status})

## Contenu extrait du site
- Titre (title): {title}
- Meta description: {meta_description}
- Lang HTML: {lang} | viewport mobile: {has_viewport} | favicon: {has_favicon}
- Nombre d'images: {n_images} | liens: {n_links}
- H1: {h1}
- H2: {h2}
- Texte (tronqué):
\"\"\"
{text}
\"\"\"

## Recherche complémentaire (web + Google Maps)
{research}

## Ta mission
Rends un rapport d'audit en **Markdown** avec EXACTEMENT ces sections:

# Audit — {name}

**Score global: X/100** (une phrase de synthèse)

## 1. Première impression & ambiance
Le site reflète-t-il bien l'activité et l'ambiance attendue ? Cohérence de marque.

## 2. UI & design (déductible du contenu/structure)
Hiérarchie, lisibilité, structure des titres, densité, images.

## 3. Contenu & copywriting
Clarté de l'offre, ton, informations manquantes (horaires, menu, prix, photos...).

## 4. Parcours utilisateur & conversion
Le visiteur peut-il facilement réserver / commander / appeler / venir ? CTA présents ?

## 5. Mobile & technique
Viewport, vitesse probable, accessibilité, balises de base, SEO local (NAP).

## 6. Confiance & preuve sociale
Avis, mise en avant de la note Google ({rating}/5), photos, mentions légales.

## 7. Recommandations priorisées
Tableau Markdown: | Priorité | Action | Impact attendu | Effort |
Liste 6 à 10 actions, triées (🔴 Critique / 🟠 Important / 🟢 Bonus).

Sois précis, cite des éléments réels du site quand c'est possible. Pas de blabla générique."""


def build_prompt(biz: Business, page: PageContent, research: Research | None) -> str:
    return AUDIT_TEMPLATE.format(
        name=biz.name,
        industry=biz.industry or "—",
        address=biz.address or "—",
        rating=biz.rating or "—",
        reviews=biz.reviews or "0",
        phone=biz.phone or biz.intl_phone or "—",
        email=biz.email or "—",
        final_url=page.final_url or biz.website,
        status=page.status,
        title=page.title or "—",
        meta_description=page.meta_description or "—",
        lang=page.lang or "—",
        has_viewport="oui" if page.has_viewport else "non",
        has_favicon="oui" if page.has_favicon else "non",
        n_images=page.n_images,
        n_links=page.n_links,
        h1=" | ".join(page.h1) or "—",
        h2=" | ".join(page.h2) or "—",
        text=page.text or "(aucun texte extrait)",
        research=research.context() if research else "(non collectée)",
    )


def run_audit(biz: Business, research: Research | None = None) -> dict:
    """Fetch + audit one business. Returns a result dict (incl. `report` text);
    writes audit.md + meta.json on success."""
    page = research.own_site if (research and research.own_site) else fetch(biz.website)
    out_dir = resolve_unique_dir(config.AUDITS_DIR, biz.slug, biz.place_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not page.ok:
        # Still useful: record that the site is down / unreachable.
        report = (
            f"# Audit — {biz.name}\n\n"
            f"**Score global: 0/100** — Le site déclaré (`{biz.website}`) est "
            f"injoignable : {page.error}.\n\n"
            "## Recommandation critique\n"
            "🔴 Le site ne répond pas. Pour un commerce local, un site indisponible "
            "équivaut à une absence de site : refonte ou remise en ligne urgente.\n"
        )
        model_used = "(none — site unreachable)"
    else:
        report = deepseek.chat(
            [
                {"role": "system", "content": AUDIT_SYSTEM},
                {"role": "user", "content": build_prompt(biz, page, research)},
            ],
            model=config.AUDIT_MODEL,
            temperature=0.4,
            max_tokens=8000,  # v4 reasoning model: budget covers reasoning + report
        )
        model_used = config.AUDIT_MODEL

    (out_dir / "audit.md").write_text(report, encoding="utf-8")
    meta = {
        "name": biz.name,
        "slug": out_dir.name,
        "place_id": biz.place_id,
        "type": "audit",
        "website": biz.website,
        "final_url": page.final_url,
        "reachable": page.ok,
        "http_status": page.status,
        "model": model_used,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "output": str(out_dir / "audit.md"), "report": report}
