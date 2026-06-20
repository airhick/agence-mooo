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

# --- API ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
GEN_MODEL = os.environ.get("DEEPSEEK_GEN_MODEL", "deepseek-v4-pro")
AUDIT_MODEL = os.environ.get("DEEPSEEK_AUDIT_MODEL", "deepseek-v4-pro")

# --- Deployment ---
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://agence.mooo.com").rstrip("/")

# --- Paths ---
CSV_PATH = ROOT / "GMAPS_SCRAPPER_BUSINESS_With_Emails.csv"
AUDITS_DIR = ROOT / "audits"      # internal deliverables (gitignored)
SITES_DIR = ROOT                  # generated sites go at repo root -> /<slug>
STATE_DIR = ROOT / "state"        # resume/progress tracking (gitignored)
RESULTS_CSV = ROOT / "results.csv"

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
