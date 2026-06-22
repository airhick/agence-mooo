"""Outreach funnel orchestrator.

Each qualified lead runs through the WHOLE funnel before the next one starts:

  1. QUALIFY  — active Google page + contact email + >=50 reviews, then per
                --target: has-site (has a site) | no-site (no site).
  2. GATHER   — research the company (own site + web + Google Maps photos/facts).
  3. AUDIT    — DeepSeek v4 audits the current site (fed the research).
  4. BUILD    — DeepSeek v4 builds a new premium site from that audit + research.
  5. PUBLISH  — push this site to GitHub (its own commit), then confirm it's live.
  6. EMAIL    — prepare a personalized package (gpt-4o copy + a gpt-image-2
               whiteboard image) in outbox/<slug>/ and create a Gmail DRAFT
               for it directly via the Gmail API (pipeline.gmail_client).

A lead's status is written to the CSV right after it finishes, so if a later
lead fails the earlier ones stay fully published and drafted.

Finished leads are stamped back into the CSV (done / error) so they are never
targeted twice. Leads that fail a target's gate are NOT stamped — they stay
re-checkable so the same lead can still qualify under the other --target.

Usage:
    python -m pipeline.run --limit 5
    python -m pipeline.run --limit 5 --target no-site
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


def select(limit: int, target: str = config.DEFAULT_TARGET) -> tuple[list[Business], int]:
    """Scan the CSV for unprocessed leads qualified for `target` (up to `limit`).

    Returns (qualified, skipped_count). Rejections are NOT persisted: qualify is
    pure-Python over the CSV (no network), so re-scanning each run is cheap, and
    not stamping skips keeps every target's candidate pool intact across runs.
    """
    qualified: list[Business] = []
    skipped = 0
    for biz in read_rows():
        if biz.is_processed:
            continue
        ok, _reason = qualify(biz, target)
        if ok:
            qualified.append(biz)
            if len(qualified) >= limit:
                break
        else:
            skipped += 1
    return qualified, skipped


# For the no-site target there is no current site to audit; tell the generator
# it is designing a FIRST web presence, not a redesign.
_NOSITE_BRIEF_NOTE = ("Ce commerce n'a PAS de site web existant. Conçois sa toute "
                      "première présence en ligne (création, pas refonte).")


def build_one(biz: Business, target: str = config.DEFAULT_TARGET) -> dict:
    """Steps 2-4 for one lead: gather -> audit -> build. Returns a result dict
    with the reserved folder, site URL and the Research (reused by the email).

    The audit step is skipped for the no-site target (no existing site to audit).
    """
    out_dir = resolve_unique_dir(config.SITES_DIR, biz.slug, biz.place_id)
    research = gather.research(biz, assets_dir=out_dir / "assets")
    if config.TARGETS[target]["needs_website"]:
        audit_report = run_audit(biz, research).get("report")
    else:
        audit_report = _NOSITE_BRIEF_NOTE
    gen_res = run_generate(
        biz, audit_report=audit_report, research=research, out_dir=out_dir)
    return {
        "out_dir": out_dir,
        "slug": out_dir.name,
        "url": gen_res["site_url"],
        "research": research,
        "research_note": ",".join(research.notes),
    }


def process_one(biz: Business, args) -> dict:
    """Run the FULL funnel for a single lead, end to end, before the next one:
    gather → audit → build → publish (its own commit) → verify → email → draft.

    Each lead is finished completely, so if a later lead fails the earlier ones
    are already published and drafted. Raises on any failure; the caller stamps
    the error and moves on to the next lead.
    """
    res = build_one(biz, args.target)
    print(f"  ✅ built {res['url']}  [research: {res['research_note']}]")

    # Step 5: publish THIS site (its own commit), then confirm it's live.
    if not args.no_push:
        publish.push_sites(message=f"Add site {res['slug']} — {_now()}")
        live = publish.verify_live(res["url"])
        print(f"  {'🟢 live' if live else '🟡 deploying'}  {res['url']}")

    # Step 6: build the email package and create the Gmail draft for this lead.
    if not args.no_mail:
        pkg = mail.prepare(biz, res["url"], research=res["research"], target=args.target)
        print(f"  ✉️  draft package ready: outbox/{biz.slug}/")
        if not args.no_draft:
            draft_id = gmail_client.create_draft(
                to=pkg["to"], subject=pkg["subject"], text=pkg["text"],
                html=pkg["html"], image_path=pkg["image"])
            print(f"  📥 Gmail draft created in {config.MOOO_FROM} (id={draft_id})")
    return res


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
    ap.add_argument("--target", choices=list(config.TARGETS), default=config.DEFAULT_TARGET,
                    help="lead segment (both need email + >=50 reviews): 'has-site' "
                         "(has a site, refresh) or 'no-site' (no site, first site)")
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

    leads, skipped = select(args.limit, args.target)
    print(f"Target '{args.target}' — {config.TARGETS[args.target]['label']}.")
    print(f"Qualified {len(leads)} lead(s) (skipped {skipped} while scanning).")
    if not leads:
        print("Nothing to process.")
        return 0

    updates: dict[str, dict] = {}
    done = 0

    # Each lead runs through the WHOLE funnel before the next one starts, and its
    # status is persisted to the CSV right after — so a failure mid-batch never
    # undoes the leads already published and drafted.
    for i, biz in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] {biz.name}  ({biz.reviews_count} avis)")
        try:
            res = process_one(biz, args)
            updates[biz.status_key] = {config.CSV_STATUS_COL: "done",
                                       config.CSV_URL_COL: res["url"], config.CSV_AT_COL: _now()}
            write_results([{"key": biz.status_key, "name": biz.name, "slug": res["slug"],
                            "status": "done", "url": res["url"],
                            "research": res["research_note"], "error": ""}])
            done += 1
        except Exception as exc:  # noqa: BLE001 - one failure must not kill the batch
            traceback.print_exc()
            updates[biz.status_key] = {config.CSV_STATUS_COL: f"error:{str(exc)[:120]}",
                                       config.CSV_AT_COL: _now()}
            write_results([{"key": biz.status_key, "name": biz.name, "slug": biz.slug,
                            "status": "error", "url": "", "research": "",
                            "error": str(exc)[:200]}])
        # Persist after every lead so progress survives a later crash.
        source.write_statuses(updates)

    u = deepseek.USAGE
    print("\n" + "=" * 60)
    print(f"Done: {done} lead(s) fully processed | {len(updates)} CSV rows stamped")
    print(f"DeepSeek calls: {u.calls} | tokens: {u.total_tokens:,}")
    if not args.no_mail and done:
        if args.no_draft:
            print("Next: create the drafts with `python -m pipeline.gmail_client drafts`.")
        else:
            print(f"Review the new drafts in {config.MOOO_FROM} and send them yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
