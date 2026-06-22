"""Outreach email package builder (step 6).

For one lead, produces an `outbox/<slug>/` package:
  - `whiteboard.png` — the blank team whiteboard photo edited by gpt-image-2 to
    handwrite a message personalized with the company name.
  - `email.json`     — {to, subject, text, html, image} ready to become a Gmail
    DRAFT. The HTML references the whiteboard inline via `cid:whiteboard`, so the
    recipient sees the image directly in the body (not as a file attachment).

Sending is intentionally NOT done here: `pipeline.gmail_client` turns the package
into a Gmail DRAFT via the Gmail API, keeping a human in the loop before sending.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config, openai_client
from .gather import Research
from .source import Business

# The fixed template the user defined; gpt-4o personalizes the wording lightly.
MAIL_SYSTEM = (
    "Tu écris des emails de prospection ultra simples, chaleureux et authentiques "
    "pour l'agence web 'Mooo' (référence à la vache, ton décontracté, tutoiement "
    "évité, vouvoiement léger et amical). Réponds STRICTEMENT en JSON valide."
)
MAIL_USER = """Rédige un court email de prospection en français pour ce commerce.

- Nom du commerce: {name}
- Lien du nouveau site (déjà en ligne, gratuit): {link}

Gabarit à respecter dans l'esprit (reste très proche, simple, 3-4 lignes max):
Objet : Nouveau site web pour {name}
« Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On est tombés sur
votre site web et on s'est dit qu'un coup de jeune lui ferait du bien — on a donc
pris la liberté de vous en créer un nouveau, gratuitement. Le voici : {link}
Dites-nous ce que vous en pensez :) »

Contraintes:
- Garde-le simple, humain, sans jargon ni superlatifs marketing.
- Inclus le lien {link} tel quel dans le corps.
- Réponds en JSON: {{"subject": "...", "body": "...(texte brut, sauts de ligne avec \\n)"}}"""

# Handwritten message to render on the blank whiteboard.
BOARD_PROMPT = (
    "Edit this photo of three people holding a blank white whiteboard in an "
    "office. Keep the people, lighting, and scene exactly the same, but write the "
    "following friendly handwritten message in black marker, neatly and clearly, "
    "centered on the whiteboard, in French:\n\n"
    "\"Bonjour {name}\n"
    "Nous c'est Mooo, on aime bien votre boite,\n"
    "donc on vous a fait un nouveau site :)\"\n\n"
    "The handwriting must be legible, well-sized to fill the board, and look like "
    "real marker writing. Do not add any other text, logos or watermarks."
)


# Lowercase TLD only -> naturally trims glued trailing junk like "...comSUIVRE".
_EMAIL_RE = re.compile(r"[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[a-z]{2,24}")
_PREFERRED = ("contact", "info", "hello", "bonjour", "accueil", "reservation",
              "reservations", "direction", "commercial", "rh")


def _first_email(raw: str) -> str:
    """Extract the best deliverable address from a noisy scraped field.

    The scraper concatenates multiple addresses and glues junk on (e.g.
    'XVIcontact@x.com, contact@x.com' or '89contact@y.frOuvert'). We collect all
    well-formed candidates (the lowercase-TLD match drops trailing garbage), then
    prefer a known business prefix, else the shortest local part (which discards
    glued prefixes like 'XVI'/'89').
    """
    seen: dict[str, str] = {}
    for m in _EMAIL_RE.findall(raw or ""):
        local, _, domain = m.partition("@")
        key = f"{local.lower()}@{domain.lower()}"
        seen.setdefault(key, f"{local}@{domain.lower()}")
    if not seen:
        return ""
    cands = list(seen.values())
    cands.sort(key=lambda e: (e.split("@")[0].lower() not in _PREFERRED,
                              len(e.split("@")[0])))
    return cands[0]


def _html_body(text: str, link: str) -> str:
    """Wrap the plain body in a minimal HTML email with the inline whiteboard on top."""
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Linkify the bare URL so it's clickable.
    safe = safe.replace(link, f'<a href="{link}">{link}</a>').replace("\n", "<br>")
    return (
        '<div style="font-family:Helvetica,Arial,sans-serif;font-size:15px;'
        'line-height:1.6;color:#1a1a1a;max-width:560px">'
        '<img src="cid:whiteboard" alt="L\'équipe Mooo" '
        'style="width:100%;max-width:560px;border-radius:12px;margin-bottom:18px">'
        f'<p>{safe}</p>'
        '</div>'
    )


def prepare(biz: Business, site_url: str, research: Research | None = None,
            out_dir: Path | None = None) -> dict:
    """Build the email package for one lead. Returns the email.json dict."""
    to = _first_email(biz.email)
    if not to:
        raise ValueError("no usable contact email")

    out_dir = out_dir or (config.OUTBOX_DIR / biz.slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Email copy via gpt-4o (JSON).
    raw = openai_client.chat(
        [{"role": "system", "content": MAIL_SYSTEM},
         {"role": "user", "content": MAIL_USER.format(name=biz.name, link=site_url)}],
        temperature=0.6, max_tokens=500,
    )
    subject, body = _parse_mail(raw, biz.name, site_url)

    # 2) Personalized whiteboard image via gpt-image-2 (edit of the blank board).
    board = out_dir / "whiteboard.png"
    png = openai_client.image_edit(
        config.WHITEBOARD_SRC, BOARD_PROMPT.format(name=biz.name), size="1024x1536")
    board.write_bytes(png)

    email = {
        "to": to,
        "subject": subject,
        "text": body,
        "html": _html_body(body, site_url),
        "image": str(board),
        "site_url": site_url,
        "name": biz.name,
    }
    (out_dir / "email.json").write_text(
        json.dumps(email, ensure_ascii=False, indent=2), encoding="utf-8")
    return email


def _parse_mail(raw: str, name: str, link: str) -> tuple[str, str]:
    """Parse the model JSON, with a safe fallback to the literal template."""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0) if m else raw)
        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()
        if subject and body and link in body:
            return subject, body
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    subject = f"Nouveau site web pour {name}"
    body = (
        f"Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On est "
        "tombés sur votre site web et on s'est dit qu'un coup de jeune lui ferait "
        "du bien — on a donc pris la liberté de vous en créer un nouveau, "
        f"gratuitement. Le voici : {link}\n\nDites-nous ce que vous en pensez :)"
    )
    return subject, body
