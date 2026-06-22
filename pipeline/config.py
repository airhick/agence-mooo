"""Configuration & lightweight .env loader (no external deps)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines, ignores comments/blank lines.

    Does not override variables already present in the real environment.
    """
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


load_env()

# --- DeepSeek (audits + site generation) ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
GEN_MODEL = os.environ.get("DEEPSEEK_GEN_MODEL", "deepseek-v4-pro")
AUDIT_MODEL = os.environ.get("DEEPSEEK_AUDIT_MODEL", "deepseek-v4-pro")

# --- OpenAI (email copy + personalized whiteboard image) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MAIL_MODEL = os.environ.get("OPENAI_MAIL_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")

# --- Outreach ---
MOOO_FROM = os.environ.get("MOOO_FROM", "globalvisionswitzerland@gmail.com")
REVIEWS_MIN = int(os.environ.get("REVIEWS_MIN", "50"))   # both targets: at least this many

# Which lead segment a run targets. Both require a contact email + REVIEWS_MIN
# reviews; they differ only by website presence and the email angle.
#   reviews_min  : inclusive minimum review count to qualify.
#   needs_website: True -> must already have a site (refonte); False -> must NOT (création).
#   mail         : which email angle in pipeline.mail to use.
TARGETS = {
    "has-site": {  # has a site -> we pitch a redesign
        "label": "site existant (refonte)",
        "reviews_min": REVIEWS_MIN,
        "needs_website": True,
        "mail": "refresh",
    },
    "no-site": {   # no site -> we pitch a first site
        "label": "sans site (création)",
        "reviews_min": REVIEWS_MIN,
        "needs_website": False,
        "mail": "create",
    },
}
DEFAULT_TARGET = "has-site"

# --- Gmail API (create outreach drafts directly in MOOO_FROM's mailbox) ---
# OAuth "Desktop app" client. Secrets live in .env (gitignored), never in git.
GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
# gmail.compose = create drafts only (no send, no read) — least privilege.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_OAUTH_PORT = int(os.environ.get("GMAIL_OAUTH_PORT", "8765"))

# --- Deployment ---
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://agence.mooo.com").rstrip("/")

# --- Paths ---
CSV_PATH = ROOT / "GMAPS_SCRAPPER_BUSINESS_With_Emails.csv"
AUDITS_DIR = ROOT / "audits"      # internal deliverables (gitignored)
SITES_DIR = ROOT                  # generated sites go at repo root -> /<slug>
STATE_DIR = ROOT / "state"        # resume/progress tracking (gitignored)
OUTBOX_DIR = ROOT / "outbox"      # per-lead email packages (gitignored)
GMAIL_TOKEN_PATH = STATE_DIR / "gmail_token.json"   # OAuth refresh token (gitignored)
RESULTS_CSV = ROOT / "results.csv"
WHITEBOARD_SRC = ROOT / "assets" / "whiteboard.png"   # blank board, edited per lead

# CSV columns the pipeline writes back so a lead is never targeted twice.
CSV_STATUS_COL = "mooo_status"    # done | skipped:<reason> | error:<msg>
CSV_URL_COL = "mooo_url"
CSV_AT_COL = "mooo_at"

# --- Runtime defaults ---
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "20"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "5"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))

# Folders that must never be turned into a site slug (avoid clobbering project files)
RESERVED_SLUGS = {
    "pipeline", "audits", "state", "node_modules", ".git", ".venv",
    "readme", "index", "assets", "css", "js", "img", "images",
}


def require_api_key() -> str:
    if not DEEPSEEK_API_KEY:
        raise SystemExit("DEEPSEEK_API_KEY missing. Set it in .env (see config.py).")
    return DEEPSEEK_API_KEY


def require_openai_key() -> str:
    if not OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY missing. Set it in .env (see config.py).")
    return OPENAI_API_KEY


def require_gmail_creds() -> tuple[str, str]:
    if not (GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET):
        raise SystemExit(
            "GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET missing. Set them in .env, then "
            "run `python -m pipeline.gmail_client auth` once to authorize.")
    return GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
