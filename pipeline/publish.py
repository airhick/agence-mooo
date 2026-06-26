"""Publish generated sites to GitHub (-> agence.mooo.com/<slug>).

Stages every root-level folder that contains an `index.html` (i.e. a generated
site), commits, and pushes to origin. Audits, the CSV, secrets and working files
are gitignored and never published.

Usage:
    python -m pipeline.publish                 # commit + push all sites
    python -m pipeline.publish --dry-run       # show what would be published
    python -m pipeline.publish -m "batch 3"    # custom commit message
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from . import config
from . import portfolio


def _git(*args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=config.ROOT, capture_output=True, text=True
    )
    if res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{res.stderr.strip()}")
    return res.stdout.strip()


def verify_live(url: str, attempts: int = 6, delay: int = 10) -> bool:
    """Poll a URL for an HTTP 200 (GitHub Pages can lag a minute after a push).

    Best-effort confirmation that a freshly pushed site is actually serving; a
    False result just means "not live yet", not that publishing failed.
    """
    for i in range(attempts):
        try:
            if requests.get(url, timeout=15, allow_redirects=True).status_code == 200:
                return True
        except requests.RequestException:
            pass
        if i < attempts - 1:
            time.sleep(delay)
    return False


def push_sites(message: str | None = None, remote: str = "origin",
               branch: str = "main", build_portfolio: bool = True) -> list[Path]:
    """Stage every root <slug>/index.html site, commit, and push. Returns the
    list of published folders (empty if there was nothing new)."""
    folders = site_folders()
    if not folders:
        return []
    # Refresh the public portfolio (thumbnails + sites.json) so the landing
    # snippet and realisations.html always reflect the sites being pushed.
    if build_portfolio:
        portfolio.build()
    for f in folders:
        _git("add", f.name)
    extras = ["README.md", ".gitignore", "requirements.txt", "pipeline",
              "index.html", "realisations.html", "sites.json"]
    present = [p for p in extras if (config.ROOT / p).exists()]
    _git("add", *present)
    if not _git("status", "--porcelain"):
        return folders  # already committed previously; treat as published
    msg = message or f"Publish {len(folders)} site(s) — {datetime.now():%Y-%m-%d %H:%M}"
    _git("commit", "-m", msg)
    _git("push", remote, branch)
    return folders


def site_folders() -> list[Path]:
    """Root-level folders holding a deployable index.html, sorted by name."""
    out = []
    for p in sorted(config.ROOT.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and (p / "index.html").exists():
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish generated sites to GitHub")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-m", "--message", default=None)
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--no-portfolio", action="store_true",
                    help="skip rebuilding thumbnails + sites.json before pushing")
    args = ap.parse_args(argv)

    folders = site_folders()
    if not folders:
        print("No generated sites found at repo root.")
        return 0

    print(f"{len(folders)} site(s) ready to publish:")
    for f in folders:
        print(f"  {config.SITE_BASE_URL}/{f.name}")

    if args.dry_run:
        print("\n(dry-run) nothing staged or pushed.")
        return 0

    push_sites(message=args.message, remote=args.remote, branch=args.branch,
               build_portfolio=not args.no_portfolio)
    print(f"\nPushed to {args.remote}/{args.branch}. Live shortly at {config.SITE_BASE_URL}/<slug>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
