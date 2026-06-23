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
    python -m pipeline.run --parallel 10            # 10 leads through the funnel at once

By default leads run one at a time. `--parallel N` runs the SAME full funnel for
N leads concurrently (threads — the work is I/O-bound: DeepSeek/OpenAI/Gmail/HTTP)
so a batch finishes in roughly the time of its slowest lead instead of the sum.
Git pushes are serialized behind a lock and every CSV write stays on the main
thread, so the bookkeeping is identical to a sequential run — just faster.
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from . import config, deepseek, gather, gmail_client, mail, publish, source
from .audit import run_audit
from .generate import run_generate
from .qualify import qualify
from .source import Business, read_rows, resolve_unique_dir

RESULT_FIELDS = ["key", "name", "slug", "status", "url", "research", "error"]

# Serializes the one resource a parallel run must not race on: git. push_sites()
# stages/commits/pushes the whole repo, so two threads pushing at once would
# collide on the index lock. Uncontended (sequential runs) the lock is a no-op.
_GIT_LOCK = threading.Lock()


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


def build_one(biz: Business, target: str = config.DEFAULT_TARGET,
              out_dir: Path | None = None) -> dict:
    """Steps 2-4 for one lead: gather -> audit -> build. Returns a result dict
    with the reserved folder, site URL and the Research (reused by the email).

    The audit step is skipped for the no-site target (no existing site to audit).

    `out_dir` is normally resolved here, but a parallel run pre-reserves the
    folder up front (see _reserve_dirs) and passes it in so two concurrent leads
    with the same slug can't both pick the same folder.
    """
    if out_dir is None:
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


def process_one(biz: Business, args, out_dir: Path | None = None) -> dict:
    """Run the FULL funnel for a single lead, end to end, before the next one:
    gather → audit → build → publish (its own commit) → verify → email → draft.

    Each lead is finished completely, so if a later lead fails the earlier ones
    are already published and drafted. Raises on any failure; the caller stamps
    the error and moves on to the next lead.

    Thread-safe: this is what a parallel run executes per worker. The only shared
    mutation is the git push, which is serialized behind _GIT_LOCK.
    """
    res = build_one(biz, args.target, out_dir=out_dir)
    print(f"  ✅ built {res['url']}  [research: {res['research_note']}]")

    # Step 5: publish THIS site (its own commit), then confirm it's live. The
    # push touches the shared git index, so only one lead pushes at a time; the
    # first to acquire the lock commits whatever sites are ready, the rest find
    # nothing new and fall through. Verification (HTTP polling) needs no lock.
    if not args.no_push:
        with _GIT_LOCK:
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


def _record_done(biz: Business, res: dict, updates: dict) -> None:
    """Stamp a finished lead into the in-memory CSV updates + the results log.

    Called only from the main thread (sequential loop or the as_completed
    collector), so the CSV writes here never need their own lock.
    """
    updates[biz.status_key] = {config.CSV_STATUS_COL: "done",
                               config.CSV_URL_COL: res["url"], config.CSV_AT_COL: _now()}
    write_results([{"key": biz.status_key, "name": biz.name, "slug": res["slug"],
                    "status": "done", "url": res["url"],
                    "research": res["research_note"], "error": ""}])


def _record_error(biz: Business, exc: Exception, updates: dict) -> None:
    """Stamp a failed lead. Same main-thread-only contract as _record_done."""
    updates[biz.status_key] = {config.CSV_STATUS_COL: f"error:{str(exc)[:120]}",
                               config.CSV_AT_COL: _now()}
    write_results([{"key": biz.status_key, "name": biz.name, "slug": biz.slug,
                    "status": "error", "url": "", "research": "",
                    "error": str(exc)[:200]}])


def _reserve_dirs(leads: list[Business]) -> list[Path]:
    """Pre-allocate one unique output folder per lead BEFORE any parallel work.

    resolve_unique_dir picks the first free slug/slug-2/... folder; run inside
    concurrent workers, two leads sharing a slug could both see it free and grab
    it. So we resolve every folder serially up front and mkdir it immediately,
    which makes the next lead's resolution see it as taken. Returns the folders
    in the same order as `leads`.
    """
    dirs: list[Path] = []
    for biz in leads:
        d = resolve_unique_dir(config.SITES_DIR, biz.slug, biz.place_id)
        d.mkdir(parents=True, exist_ok=True)
        dirs.append(d)
    return dirs


def run_sequential(leads: list[Business], args) -> tuple[dict, int]:
    """Original behaviour: each lead runs the WHOLE funnel before the next one,
    its status persisted right after — so a mid-batch failure never undoes the
    leads already published and drafted."""
    updates: dict[str, dict] = {}
    done = 0
    for i, biz in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] {biz.name}  ({biz.reviews_count} avis)")
        try:
            res = process_one(biz, args)
            _record_done(biz, res, updates)
            done += 1
        except Exception as exc:  # noqa: BLE001 - one failure must not kill the batch
            traceback.print_exc()
            _record_error(biz, exc, updates)
        # Persist after every lead so progress survives a later crash.
        source.write_statuses(updates)
    return updates, done


def run_parallel(leads: list[Business], args) -> tuple[dict, int]:
    """Run the SAME funnel as run_sequential, but for up to `args.parallel` leads
    at once. Each lead is one worker thread (the work is I/O-bound); folders are
    reserved up front, the git push is serialized in process_one via _GIT_LOCK,
    and results are collected on THIS (main) thread as workers finish — so every
    CSV write stays single-threaded and the bookkeeping matches a serial run.
    """
    dirs = _reserve_dirs(leads)
    updates: dict[str, dict] = {}
    done = 0
    n = len(leads)
    workers = min(args.parallel, n)
    print(f"\nLaunching {n} lead(s) through the funnel, {workers} at a time…")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_one, biz, args, out_dir): biz
                   for biz, out_dir in zip(leads, dirs)}
        # Collect each lead as it returns ("catch all processes when they come
        # back"), in completion order rather than launch order.
        for k, fut in enumerate(as_completed(futures), 1):
            biz = futures[fut]
            try:
                res = fut.result()
                print(f"[{k}/{n}] ✅ done  {biz.name}  ({biz.reviews_count} avis)")
                _record_done(biz, res, updates)
                done += 1
            except Exception as exc:  # noqa: BLE001 - one failure must not kill the batch
                print(f"[{k}/{n}] ❌ failed  {biz.name}: {exc}")
                traceback.print_exc()
                _record_error(biz, exc, updates)
            # Persist after every completion so progress survives a later crash.
            source.write_statuses(updates)
    return updates, done


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
    ap.add_argument("--parallel", type=int, default=1, metavar="N",
                    help="run N leads through the WHOLE funnel concurrently "
                         "(default 1 = sequential). E.g. --parallel 10 builds 10 "
                         "sites at once; --limit is raised to N if it's lower.")
    args = ap.parse_args(argv)

    if args.parallel < 1:
        ap.error("--parallel must be >= 1")
    # "Launch 10 in parallel" implies wanting 10 leads, so don't let a smaller
    # --limit starve the pool — raise it to match the requested width.
    if args.limit < args.parallel:
        print(f"--limit {args.limit} < --parallel {args.parallel}; raising --limit to {args.parallel}.")
        args.limit = args.parallel

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

    if args.parallel > 1:
        updates, done = run_parallel(leads, args)
    else:
        updates, done = run_sequential(leads, args)

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
