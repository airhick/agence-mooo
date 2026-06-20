"""Batch orchestrator.

For each business in the CSV: route to AUDIT (has website) or GENERATE (no
website), process in concurrent batches, track progress for resume, and write a
master results.csv index.

Usage:
    python -m pipeline.run --limit 5
    python -m pipeline.run --limit 200 --batch-size 20 --workers 5
    python -m pipeline.run --only generate --limit 50
    python -m pipeline.run --resume        # skip already-processed businesses
"""
from __future__ import annotations

import argparse
import csv
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config, deepseek, state
from .audit import run_audit
from .generate import run_generate
from .source import Business, read_rows

RESULT_FIELDS = ["key", "name", "slug", "type", "status", "output", "url", "error"]


def _key(biz: Business) -> str:
    return biz.place_id or f"slug:{biz.slug}"


def _process_one(biz: Business, only: str) -> dict:
    route = "audit" if biz.has_website else "generate"
    if only != "both" and only != route:
        return {"key": _key(biz), "name": biz.name, "slug": biz.slug,
                "type": route, "status": "skipped", "output": "", "url": "", "error": ""}
    try:
        if route == "audit":
            res = run_audit(biz)
            url = res.get("final_url", "")
        else:
            res = run_generate(biz)
            url = res.get("site_url", "")
        return {"key": _key(biz), "name": biz.name, "slug": biz.slug, "type": route,
                "status": "ok", "output": res.get("output", ""), "url": url, "error": ""}
    except Exception as exc:  # noqa: BLE001 - one failure must not kill the batch
        traceback.print_exc()
        return {"key": _key(biz), "name": biz.name, "slug": biz.slug, "type": route,
                "status": "error", "output": "", "url": "", "error": str(exc)[:300]}


def select(limit: int, only: str, resume: bool) -> list[Business]:
    done = state.load_done() if resume else set()
    picked: list[Business] = []
    seen_slugs: set[str] = set()
    for biz in read_rows():
        if _key(biz) in done:
            continue
        route = "audit" if biz.has_website else "generate"
        if only != "both" and only != route:
            continue
        # Avoid two businesses writing to the same slug folder in one run.
        if biz.slug in seen_slugs:
            continue
        seen_slugs.add(biz.slug)
        picked.append(biz)
        if len(picked) >= limit:
            break
    return picked


def write_results(rows: list[dict]) -> None:
    new = not config.RESULTS_CSV.exists()
    with open(config.RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agence Mooo website pipeline")
    ap.add_argument("--limit", type=int, default=5, help="max businesses this run")
    ap.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    ap.add_argument("--workers", type=int, default=config.MAX_WORKERS)
    ap.add_argument("--only", choices=["audit", "generate", "both"], default="both")
    ap.add_argument("--resume", action="store_true", help="skip processed businesses")
    args = ap.parse_args(argv)

    config.require_api_key()
    businesses = select(args.limit, args.only, args.resume)
    if not businesses:
        print("Nothing to process (check --only / --resume).")
        return 0

    n = len(businesses)
    print(f"Selected {n} businesses | only={args.only} | "
          f"batch={args.batch_size} workers={args.workers}")
    all_results: list[dict] = []

    for start in range(0, n, args.batch_size):
        batch = businesses[start:start + args.batch_size]
        print(f"\n=== Batch {start // args.batch_size + 1} "
              f"({start + 1}-{start + len(batch)} / {n}) ===")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_process_one, b, args.only): b for b in batch}
            for fut in as_completed(futures):
                res = fut.result()
                if res["status"] == "ok":
                    state.record(res["key"], res)
                icon = {"ok": "✅", "error": "❌", "skipped": "⏭️"}.get(res["status"], "?")
                tail = res["url"] or res["output"] or res["error"]
                print(f"  {icon} [{res['type']:8}] {res['name'][:40]:40} {tail}")
                all_results.append(res)

    write_results(all_results)

    ok = sum(r["status"] == "ok" for r in all_results)
    err = sum(r["status"] == "error" for r in all_results)
    gen = sum(r["status"] == "ok" and r["type"] == "generate" for r in all_results)
    aud = sum(r["status"] == "ok" and r["type"] == "audit" for r in all_results)
    u = deepseek.USAGE
    print("\n" + "=" * 60)
    print(f"Done: {ok} ok ({gen} sites generated, {aud} audits), {err} errors")
    print(f"DeepSeek calls: {u.calls} | tokens: {u.total_tokens:,} "
          f"(in {u.prompt_tokens:,} / out {u.completion_tokens:,})")
    print(f"Results index: {config.RESULTS_CSV}")
    return 1 if err and not ok else 0


if __name__ == "__main__":
    sys.exit(main())
