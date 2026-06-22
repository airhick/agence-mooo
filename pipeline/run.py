"""Outreach funnel orchestrator.

For each lead in the CSV, runs the full pipeline:

  1. QUALIFY  — >100 reviews, active Google page, contact email, existing site.
  2. GATHER   — research the company (own site + web + Google Maps photos/facts).
  3. AUDIT    — DeepSeek v4 audits the current site (fed the research).
  4. BUILD    — DeepSeek v4 builds a new premium site from that audit + research.
  5. PUBLISH  — push all new sites to GitHub once, then confirm they're live.
  6. EMAIL    — prepare a personalized package (gpt-4o copy + a gpt-image-2
               whiteboard image) in outbox/<slug>/ and create a Gmail DRAFT
               for it directly via the Gmail API (pipeline.gmail_client).

Processed leads are stamped back into the CSV (mooo_status / mooo_url / mooo_at)
so they are never targeted twice. Disqualified leads scanned while filling the
batch are stamped `skipped:<reason>` for the same reason.

Usage:
    python -m pipeline.run --limit 5
    python -m pipeline.run --limit 10 --no-push     # build locally, don't push
    python -m pipeline.run --limit 5 --no-mail      # skip email packages
"""
from __future__ import annotations

import argparse
import csv
import sys
import traceback
from datetime import datetime

from . import config, deepseek, gather, gmail_client, mail, publish, source
from .audit import run_audit
from .generate import run_generate
from .qualify import qualify
from .source import Business, read_rows, resolve_unique_dir

RESULT_FIELDS = ["key", "name", "slug", "status", "url", "research", "error"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def select(limit: int) -> tuple[list[Business], dict]:
    """Scan the CSV for unprocessed, qualified leads (up to `limit`).

    Returns (qualified, skip_updates) where skip_updates stamps every lead we
    examined and rejected so the next run doesn't re-check it.
    """
    qualified: list[Business] = []
    skips: dict[str, dict] = {}
    for biz in read_rows():
        if biz.is_processed:
            continue
        ok, reason = qualify(biz)
        if ok:
            qualified.append(biz)
            if len(qualified) >= limit:
                break
        else:
            skips[biz.status_key] = {
                config.CSV_STATUS_COL: f"skipped:{reason}", config.CSV_AT_COL: _now()}
    return qualified, skips


def build_one(biz: Business) -> dict:
    """Steps 2-4 for one lead: gather -> audit -> build. Returns a result dict
    with the reserved folder, site URL and the Research (reused by the email)."""
    out_dir = resolve_unique_dir(config.SITES_DIR, biz.slug, biz.place_id)
    research = gather.research(biz, assets_dir=out_dir / "assets")
    audit_res = run_audit(biz, research)
    gen_res = run_generate(
        biz, audit_report=audit_res.get("report"), research=research, out_dir=out_dir)
    return {
        "out_dir": out_dir,
        "slug": out_dir.name,
        "url": gen_res["site_url"],
        "research": research,
        "research_note": ",".join(research.notes),
    }


def write_results(rows: list[dict]) -> None:
    new = not config.RESULTS_CSV.exists()
    with open(config.RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agence Mooo outreach funnel")
    ap.add_argument("--limit", type=int, default=5, help="qualified leads this run")
    ap.add_argument("--no-push", action="store_true", help="build locally, don't push to GitHub")
    ap.add_argument("--no-mail", action="store_true", help="skip email packages")
    ap.add_argument("--no-draft", action="store_true",
                    help="build email packages but don't create Gmail drafts")
    args = ap.parse_args(argv)

    config.require_api_key()
    if not args.no_mail:
        config.require_openai_key()
        if not args.no_draft:
            config.require_gmail_creds()

    leads, skips = select(args.limit)
    print(f"Qualified {len(leads)} lead(s) (skipped {len(skips)} while scanning).")
    if not leads:
        source.write_statuses(skips)
        print("Nothing to process.")
        return 0

    updates: dict[str, dict] = dict(skips)
    results: list[dict] = []
    built: list[dict] = []   # leads whose site built OK (for push + email)

    # Steps 2-4: gather -> audit -> build (sequential; each lead is heavy).
    for i, biz in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] {biz.name}  ({biz.reviews_count} avis)")
        try:
            res = build_one(biz)
            res["biz"] = biz
            built.append(res)
            print(f"  ✅ built {res['url']}  [research: {res['research_note']}]")
            results.append({"key": biz.status_key, "name": biz.name, "slug": res["slug"],
                            "status": "built", "url": res["url"],
                            "research": res["research_note"], "error": ""})
        except Exception as exc:  # noqa: BLE001 - one failure must not kill the batch
            traceback.print_exc()
            updates[biz.status_key] = {config.CSV_STATUS_COL: f"error:{str(exc)[:120]}",
                                       config.CSV_AT_COL: _now()}
            results.append({"key": biz.status_key, "name": biz.name, "slug": biz.slug,
                            "status": "error", "url": "", "research": "",
                            "error": str(exc)[:200]})

    # Step 5: push all new sites at once, then confirm liveness.
    if built and not args.no_push:
        print(f"\nPublishing {len(built)} site(s) to GitHub…")
        publish.push_sites(message=f"Add {len(built)} site(s) — {_now()}")
        for res in built:
            live = publish.verify_live(res["url"])
            print(f"  {'🟢 live' if live else '🟡 deploying'}  {res['url']}")

    # Step 6: build the email package and create the Gmail draft for each lead.
    for res in built:
        biz = res["biz"]
        if not args.no_mail:
            try:
                pkg = mail.prepare(biz, res["url"], research=res["research"])
                print(f"  ✉️  draft package ready: outbox/{biz.slug}/")
                if not args.no_draft:
                    draft_id = gmail_client.create_draft(
                        to=pkg["to"], subject=pkg["subject"], text=pkg["text"],
                        html=pkg["html"], image_path=pkg["image"])
                    print(f"  📥 Gmail draft created in {config.MOOO_FROM} (id={draft_id})")
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                updates[biz.status_key] = {config.CSV_STATUS_COL: f"error:mail:{str(exc)[:100]}",
                                           config.CSV_URL_COL: res["url"], config.CSV_AT_COL: _now()}
                continue
        updates[biz.status_key] = {config.CSV_STATUS_COL: "done",
                                   config.CSV_URL_COL: res["url"], config.CSV_AT_COL: _now()}

    # Persist all statuses back to the CSV in one rewrite, and the run index.
    n = source.write_statuses(updates)
    write_results(results)

    done = sum(1 for u in updates.values() if u.get(config.CSV_STATUS_COL) == "done")
    u = deepseek.USAGE
    print("\n" + "=" * 60)
    print(f"Done: {done} lead(s) fully processed | {len(updates)} CSV rows stamped ({n} written)")
    print(f"DeepSeek calls: {u.calls} | tokens: {u.total_tokens:,}")
    if not args.no_mail and built:
        if args.no_draft:
            print("Next: create the drafts with `python -m pipeline.gmail_client drafts`.")
        else:
            print(f"Review the new drafts in {config.MOOO_FROM} and send them yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
