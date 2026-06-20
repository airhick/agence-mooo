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
from datetime import datetime
from pathlib import Path

from . import config


def _git(*args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=config.ROOT, capture_output=True, text=True
    )
    if res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{res.stderr.strip()}")
    return res.stdout.strip()


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

    for f in folders:
        _git("add", f.name)
    # README/pipeline changes too, but never the gitignored data/secrets.
    _git("add", "README.md", ".gitignore", "requirements.txt", "pipeline")

    status = _git("status", "--porcelain")
    if not status:
        print("\nNothing new to commit (already published).")
        return 0

    msg = args.message or f"Publish {len(folders)} site(s) — {datetime.now():%Y-%m-%d %H:%M}"
    _git("commit", "-m", msg)
    print(f"\nCommitted: {msg}")
    _git("push", args.remote, args.branch)
    print(f"Pushed to {args.remote}/{args.branch}. Live shortly at {config.SITE_BASE_URL}/<slug>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
