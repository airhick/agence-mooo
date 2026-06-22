# Agence Mooo — automated outreach funnel

Reads scraped French businesses from a CSV and, for each **qualified** lead, runs
a full outreach funnel in one command:

1. **Qualify** — keep only leads with an **active Google page** (Place ID +
   rating), a **contact email**, and **≥50 reviews**, then split by the chosen
   **`--target`**:
   - **`has-site`** (default): has an **existing website** → the email pitches a
     *refonte* ("we redesigned your site").
   - **`no-site`**: has **no website** → the email pitches a *first site* ("you
     had no site, so we built you one"), and the audit step is skipped.

   Leads that fail a target's gate are **not** stamped, so a no-website lead is
   still available to a later `no-site` run. `pipeline/qualify.py`.
2. **Gather** — research the company: its own site, a keyless web search, and its
   **Google Maps page** (real photos + facts) via headless Playwright. Photos are
   downloaded into the site folder. `pipeline/gather.py`.
3. **Audit** — **DeepSeek v4** audits the current site, fed the gathered research,
   and writes a French report. `pipeline/audit.py`.
4. **Build** — **DeepSeek v4** builds a new premium single-page site **from that
   audit** (+ research + real photos), placed at the repo root (`<slug>/index.html`)
   so it serves at `agence.mooo.com/<slug>`. `pipeline/generate.py`.
5. **Publish** — push every new site to GitHub once, then confirm it's live.
   `pipeline/publish.py`.
6. **Email** — prepare a personalized package per lead in `outbox/<slug>/` (copy
   written by **gpt-4o**, team **whiteboard photo** edited by **gpt-image-2** to
   handwrite a message with the company name, embedded **inline** in the HTML body
   via `cid:whiteboard`) and create a **Gmail draft** for it directly through the
   **Gmail API** in `MOOO_FROM`. `pipeline/mail.py` + `pipeline/gmail_client.py`.

> **Who generates what:** DeepSeek v4 produces every per-business audit and site;
> OpenAI (gpt-4o / gpt-image-2) produces the outreach email copy and image. The
> Python pipeline only orchestrates.

Every processed lead is stamped back into the CSV (`mooo_status` / `mooo_url` /
`mooo_at`) so it's **never targeted twice**; leads rejected while scanning are
stamped `skipped:<reason>`.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/playwright install chromium      # for Google Maps research (optional)
```

`.env` (gitignored):

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_GEN_MODEL=deepseek-v4-pro
DEEPSEEK_AUDIT_MODEL=deepseek-v4-pro
OPENAI_API_KEY=sk-...
OPENAI_MAIL_MODEL=gpt-4o
OPENAI_IMAGE_MODEL=gpt-image-2
MOOO_FROM=globalvisionswitzerland@gmail.com
GMAIL_CLIENT_ID=...apps.googleusercontent.com   # OAuth "Desktop app" client
GMAIL_CLIENT_SECRET=GOCSPX-...
SITE_BASE_URL=https://agence.mooo.com
```

**Authorize Gmail once** (so the funnel can create drafts in `MOOO_FROM`):

```bash
./.venv/bin/python -m pipeline.gmail_client auth
```

This opens Google's consent screen, then stores a refresh token in
`state/gmail_token.json` (gitignored). The OAuth scope is `gmail.compose` —
**create drafts only**: the app can't send or read your mail. Create the OAuth
client (type **Desktop app**) in the Google Cloud Console → APIs & Services →
Credentials, with the Gmail API enabled.

## Run

```bash
./.venv/bin/python -m pipeline.run --limit 5        # full funnel on 5 leads (has-site)
./.venv/bin/python -m pipeline.run --limit 10       # next 10 (skips done leads)
./.venv/bin/python -m pipeline.run --limit 5 --target no-site  # ≥50 reviews, no website
./.venv/bin/python -m pipeline.run --limit 5 --no-push   # build locally only
./.venv/bin/python -m pipeline.run --limit 5 --no-mail    # skip email packages
./.venv/bin/python -m pipeline.run --limit 5 --no-draft  # build packages, don't draft
```

Each run picks the next unprocessed, qualified leads, builds + pushes their sites,
drops a package in `outbox/<slug>/`, and creates a **Gmail draft** for it in
`MOOO_FROM`.

## The drafts

`pipeline.run` creates the Gmail draft for each lead automatically (step 6) but
**never sends** — you review and send each one yourself from Gmail. The
whiteboard image is embedded **inline** in the body (`cid:whiteboard`), not
attached. To (re)create drafts from an existing `outbox/` without re-running the
funnel:

```bash
./.venv/bin/python -m pipeline.gmail_client drafts            # every outbox/<slug>/
./.venv/bin/python -m pipeline.gmail_client drafts <slug> ... # specific leads
```

## Outputs

| Path | What | Deployed? |
|------|------|-----------|
| `<slug>/index.html` + `<slug>/assets/` | Generated site (+ real Maps photos) | ✅ `agence.mooo.com/<slug>` |
| `<slug>/brief.md` | Creative brief used to build it | ✅ (harmless) |
| `audits/<slug>/audit.md` | DeepSeek audit feeding the build | ❌ local only |
| `outbox/<slug>/email.json` + `whiteboard.png` | Email draft package | ❌ local only |
| `GMAPS_..._With_Emails.csv` | Source CSV, stamped with `mooo_status` | ❌ private |
| `results.csv` | Per-run index | ❌ local only |

## Architecture (`pipeline/`)

- `config.py` — `.env` loader, DeepSeek + OpenAI models, paths, qualify threshold.
- `source.py` — CSV → `Business` records; reviews parsing; CSV status write-back.
- `qualify.py` — the lead gate (reviews / Google page / email / website).
- `gather.py` — company research (own site + web + Maps photos), graceful fallback.
- `deepseek.py` / `openai_client.py` — model clients with retries/backoff.
- `fetcher.py` — fetch + extract content from existing sites.
- `audit.py` — audit prompt (with research) → `audit.md`.
- `generate.py` — two-pass build chained from the audit → `index.html` + `brief.md`.
- `mail.py` — gpt-4o copy + gpt-image-2 whiteboard → `outbox/<slug>/` package.
- `gmail_client.py` — Gmail API: one-time OAuth (`auth`) + create inline-image drafts.
- `publish.py` — push root `<slug>` sites to GitHub + liveness check.
- `run.py` — funnel orchestrator + CLI.

## Notes

- DeepSeek v4 is a **reasoning, text-only** model: audits/sites reason over the
  extracted text + research; real imagery comes from Google Maps (or curated
  stock fallback in `assets.py`).
- Google Maps scraping is best-effort; if Playwright isn't installed or the page
  is blocked, the site falls back to curated stock photos and the funnel continues.
- Cost per lead ≈ 2 DeepSeek calls (audit + build) + 1 gpt-4o + 1 gpt-image-2.
```
