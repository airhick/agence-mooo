# Agence Mooo — automated website pipeline

Reads scraped French businesses from a CSV and, for each one:

- **Has a website** → fetches it and writes a French **audit report** (UI,
  content, user journey, mobile/SEO, trust, prioritized actions) with DeepSeek.
- **No website** → generates a **premium, deployable single-page site** placed at
  the repo root (`<slug>/index.html`) so it serves at `agence.mooo.com/<slug>`.

Runs in **resumable batches** with concurrency, retries, and progress tracking.

## Premium generation (two-pass)

Sites are built to look like a studio's €10k work, not generic AI output:

1. **Pass A — Art direction** (`deepseek-v4-pro`, reasoning): commits to a bold,
   context-specific aesthetic and writes a French creative brief + real copy
   (concept, palette in HEX, editorial tone, hero line, section-by-section text,
   a memorable visual signature).
2. **Pass B — Build**: turns the brief into a production-grade page using:
   - **Real curated photography** — `pipeline/assets.py` holds Unsplash photo IDs
     verified to return 200, keyed by industry, so the model never invents broken
     image URLs.
   - **Distinctive Google Font pairings** (varied per business — never
     Inter/Roboto/Arial).
   - Motion (staggered load reveals + scroll `IntersectionObserver`), atmosphere
     (grain/gradient/shadow), expressive typography, mobile-first responsive.

Quality principles come from the `frontend-design` skill, baked into the prompts.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
# Put your DeepSeek key in .env (gitignored).
```

`.env`:

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_GEN_MODEL=deepseek-v4-pro      # reasoning model; high token budget
DEEPSEEK_AUDIT_MODEL=deepseek-v4-pro
SITE_BASE_URL=https://agence.mooo.com
```

## Run

```bash
./.venv/bin/python -m pipeline.run --limit 5                       # pilot
./.venv/bin/python -m pipeline.run --limit 200 --batch-size 20 --workers 5
./.venv/bin/python -m pipeline.run --only generate --limit 50
./.venv/bin/python -m pipeline.run --only audit --limit 50
./.venv/bin/python -m pipeline.run --limit 1000 --resume          # skip done
```

Preview a generated site locally:

```bash
./.venv/bin/python -m http.server 8777   # then open localhost:8777/<slug>/
```

## Outputs

| Path | What | Deployed? |
|------|------|-----------|
| `<slug>/index.html` | Generated premium site | ✅ `agence.mooo.com/<slug>` |
| `<slug>/brief.md` | Creative brief used to build it | ✅ (harmless) |
| `audits/<slug>/audit.md` | Audit report for existing sites | ❌ local only |
| `results.csv` | Master index of processed businesses | ❌ local only |
| `state/processed.jsonl` | Resume log | ❌ local only |

## Architecture (`pipeline/`)

- `config.py` — `.env` loader, models, paths, runtime defaults.
- `deepseek.py` — OpenAI-compatible client, retries/backoff, token tracking.
- `source.py` — CSV → clean `Business` records, routing flag, URL slug.
- `assets.py` — verified Unsplash imagery + Google Font pairings per industry.
- `fetcher.py` — fetch + extract content from existing sites (for audits).
- `audit.py` — audit prompt → `audit.md` + `meta.json`.
- `generate.py` — two-pass premium site build → `index.html` + `brief.md` + meta.
- `state.py` — resumable progress log.
- `run.py` — batch orchestrator + CLI.

## Folders & deploy

Every processed business is **one folder**, named by a URL slug derived from its
name. Re-runs update the same folder (matched by Google Place ID); two different
businesses never collide (`le-cafe`, `le-cafe-2`, ...).

- **Generated sites** live at the **repo root**: `<slug>/index.html` → served at
  `agence.mooo.com/<slug>`. That's the clean link you send the client.
- **Audits** live under `audits/<slug>/` and stay **private** (gitignored) —
  they critique someone else's existing site, so they're sales material, not
  something to host publicly.

Publish all generated sites with one command:

```bash
./.venv/bin/python -m pipeline.publish --dry-run    # preview the URLs
./.venv/bin/python -m pipeline.publish              # commit + push to GitHub
```

It stages only root folders containing an `index.html`, commits, and pushes to
`github.com/airhick/agence-mooo` (GitHub Pages → `agence.mooo.com`). The CSV,
audits, `.env`, and state files are gitignored and never leave your machine.

## Notes

- DeepSeek v4 is a **reasoning** model and **text-only** (no vision), so audits
  reason over extracted HTML/text and generated sites are art-directed via the
  brief rather than visual feedback.
- A full premium site = 2 DeepSeek calls (~20–25k tokens, ~2–3 min). Budget
  accordingly before a large run.
