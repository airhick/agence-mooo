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
{gabarit}

Contraintes:
- Garde-le simple, humain, sans jargon ni superlatifs marketing.
- Inclus le lien {link} tel quel dans le corps.
- Réponds en JSON: {{"subject": "...", "body": "...(texte brut, sauts de ligne avec \\n)"}}"""

# One angle per target segment (see config.TARGETS):
#  - "refresh": the business already has a site -> we redesigned it.
#  - "create" : the business has no site -> we built its first one.
# Each angle supplies the gabarit shown to gpt-4o plus a literal fallback used
# verbatim if the model's JSON is unusable. {name}/{link} are filled in prepare().
MAIL_ANGLES = {
    "refresh": {
        "subject": "Nouveau site web pour {name}",
        "gabarit": (
            "Objet : Nouveau site web pour {name}\n"
            "« Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On est "
            "tombés sur votre site web et on s'est dit qu'un coup de jeune lui ferait "
            "du bien — on a donc pris la liberté de vous en créer un nouveau, "
            "gratuitement. Le voici : {link}\n"
            "Dites-nous ce que vous en pensez :) »"),
        "fallback": (
            "Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On est "
            "tombés sur votre site web et on s'est dit qu'un coup de jeune lui ferait "
            "du bien — on a donc pris la liberté de vous en créer un nouveau, "
            "gratuitement. Le voici : {link}\n\nDites-nous ce que vous en pensez :)"),
    },
    "create": {
        "subject": "Un site web pour {name}",
        "gabarit": (
            "Objet : Un site web pour {name}\n"
            "« Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On a vu "
            "que vous n'aviez pas encore de site web — vu vos avis, ce serait dommage ! "
            "On a donc pris la liberté de vous en créer un, gratuitement. Le voici : "
            "{link}\n"
            "Dites-nous ce que vous en pensez :) »"),
        "fallback": (
            "Bonjour {name}, nous sommes l'agence Mooo (comme la vache). On a vu que "
            "vous n'aviez pas encore de site web — vu vos avis, ce serait dommage ! On "
            "a donc pris la liberté de vous en créer un, gratuitement. Le voici : "
            "{link}\n\nDites-nous ce que vous en pensez :)"),
    },
}

# Handwritten message to render on the blank whiteboard.
BOARD_PROMPT = (
    "Edit this photo of three people holding a blank white whiteboard in an "
    "office. Keep the people, lighting, and scene exactly the same, but write the "
    "following message on the whiteboard in black marker, in French, as if it were "
    "written by hand: messy, bad handwriting that is not consistent (uneven letter "
    "sizes, sloppy spacing, not perfectly straight lines), with a light reflection "
    "glare on the whiteboard surface and faint eraser stains and smudges left over "
    "from other writings that were wiped off. The text reads:\n\n"
    "\"Bonjour {name}\n"
    "Nous c'est Mooo, on aime bien votre boite,\n"
    "donc on vous a fait un nouveau site :)\"\n\n"
    "Keep it readable but clearly hand-written and natural. Do not add any other "
    "text, logos or watermarks. Keep the people's faces imperfect and unretouched, "
    "as if it were a Friday afternoon — natural, relaxed, candid facial expressions."
)


# Email signature footer: Mooo logo + website + contact address. The logo is
# served from the live site so it needs no extra inline attachment.
_LOGO_URL = f"{config.SITE_BASE_URL}/logomooo.png"
_FOOTER_SITE = config.SITE_BASE_URL.split("//", 1)[-1]   # "agence.mooo.com"
_FOOTER_EMAIL = "agencemooo@gmail.com"
_FOOTER_TEXT = f"\n\n—\nAgence Mooo · {config.SITE_BASE_URL.split('//', 1)[-1]} · {_FOOTER_EMAIL}"
_FOOTER_HTML = (
    '<div style="margin-top:28px;padding-top:18px;border-top:1px solid #eaeaea;'
    'color:#888;font-size:13px;line-height:1.5">'
    f'<img src="{_LOGO_URL}" alt="Agence Mooo" width="40" height="40" '
    'style="vertical-align:middle;margin-right:12px;border-radius:8px">'
    '<span style="vertical-align:middle">'
    '<strong style="color:#1a1a1a">Agence Mooo</strong><br>'
    f'<a href="{config.SITE_BASE_URL}" style="color:#888;text-decoration:none">{_FOOTER_SITE}</a>'
    '&nbsp;·&nbsp;'
    f'<a href="mailto:{_FOOTER_EMAIL}" style="color:#888;text-decoration:none">{_FOOTER_EMAIL}</a>'
    '</span></div>'
)


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
        f'{_FOOTER_HTML}'
        '</div>'
    )


def prepare(biz: Business, site_url: str, research: Research | None = None,
            out_dir: Path | None = None,
            target: str = config.DEFAULT_TARGET) -> dict:
    """Build the email package for one lead. Returns the email.json dict.

    `target` selects the message angle (see config.TARGETS / MAIL_ANGLES): a
    "refresh" pitch for businesses that already had a site, a "create" pitch for
    those that had none.
    """
    # Address every well-formed contact inbox for the business (best first),
    # comma-joined into a single To header. qualify() already guarantees >=1.
    recipients = biz.emails
    if not recipients:
        raise ValueError("no usable contact email")
    to = ", ".join(recipients)

    out_dir = out_dir or (config.OUTBOX_DIR / biz.slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    angle = MAIL_ANGLES[config.TARGETS[target]["mail"]]
    gabarit = angle["gabarit"].format(name=biz.name, link=site_url)

    # 1) Email copy via gpt-4o (JSON).
    raw = openai_client.chat(
        [{"role": "system", "content": MAIL_SYSTEM},
         {"role": "user", "content": MAIL_USER.format(
             name=biz.name, link=site_url, gabarit=gabarit)}],
        temperature=0.6, max_tokens=500,
    )
    subject, body = _parse_mail(
        raw, site_url,
        angle["subject"].format(name=biz.name),
        angle["fallback"].format(name=biz.name, link=site_url))

    # 2) Personalized whiteboard image via gpt-image-2 (edit of the blank board).
    board = out_dir / "whiteboard.png"
    png = openai_client.image_edit(
        config.WHITEBOARD_SRC, BOARD_PROMPT.format(name=biz.name), size="1024x1536")
    board.write_bytes(png)

    email = {
        "to": to,
        "subject": subject,
        "text": body + _FOOTER_TEXT,
        "html": _html_body(body, site_url),
        "image": str(board),
        "site_url": site_url,
        "name": biz.name,
    }
    (out_dir / "email.json").write_text(
        json.dumps(email, ensure_ascii=False, indent=2), encoding="utf-8")
    return email


def _parse_mail(raw: str, link: str, fallback_subject: str,
                fallback_body: str) -> tuple[str, str]:
    """Parse the model JSON, with a safe fallback to the angle's literal template."""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0) if m else raw)
        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()
        if subject and body and link in body:
            return subject, body
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return fallback_subject, fallback_body
