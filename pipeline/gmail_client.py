"""Native Gmail API client — creates outreach drafts directly in MOOO_FROM.

Replaces the previous "create the draft via the Gmail MCP" manual step. Each
`outbox/<slug>/` package built by `pipeline.mail` becomes a real Gmail DRAFT in
the configured mailbox, with the personalized whiteboard embedded inline in the
HTML body (`cid:whiteboard`). Drafts are NOT sent — a human still reviews and
sends each one from Gmail.

Auth (one-time):
    python -m pipeline.gmail_client auth
Runs an OAuth "Desktop app" loopback flow in the browser and stores a refresh
token in `state/gmail_token.json`. After that, draft creation is non-interactive.

Process an existing outbox without re-running the funnel:
    python -m pipeline.gmail_client drafts            # all outbox/<slug>/
    python -m pipeline.gmail_client drafts <slug> ...  # specific leads

Uses only stdlib + `requests` (already a dependency) — no google-auth needed.
The OAuth scope is `gmail.compose`: create drafts only, no send and no read.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.parse
import webbrowser
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

from . import config

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRAFTS_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"

# In-process access-token cache: (token, expiry_epoch).
_ACCESS: tuple[str, float] = ("", 0.0)


class GmailError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# OAuth: one-time authorization + token refresh
# --------------------------------------------------------------------------- #
def _redirect_uri() -> str:
    return f"http://localhost:{config.GMAIL_OAUTH_PORT}/"


def authorize() -> None:
    """Interactive loopback OAuth flow → store a refresh token in state/.

    Requires an OAuth client of type "Desktop app" (loopback redirect needs no
    pre-registration). Opens the consent screen in the browser, captures the
    auth code on localhost, exchanges it, and writes the refresh token.
    """
    client_id, client_secret = config.require_gmail_creds()
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": config.GMAIL_SCOPE,
        "access_type": "offline",     # ask for a refresh token
        "prompt": "consent",          # force a refresh token even on re-auth
    }
    auth_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    code_box: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            code_box["code"] = (params.get("code") or [""])[0]
            code_box["error"] = (params.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Authorization failed: " + code_box["error"]) if code_box["error"] \
                else "Mooo is authorized. You can close this tab."
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *_args):  # silence the default stderr logging
            pass

    server = HTTPServer(("localhost", config.GMAIL_OAUTH_PORT), _Handler)
    print(f"Opening browser to authorize Gmail for {config.MOOO_FROM} …")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)
    server.handle_request()   # serve exactly one request (the redirect)
    server.server_close()

    if code_box.get("error"):
        raise GmailError(f"OAuth denied: {code_box['error']}")
    code = code_box.get("code")
    if not code:
        raise GmailError("No authorization code received on the loopback redirect.")

    r = requests.post(TOKEN_ENDPOINT, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    }, timeout=30)
    if r.status_code != 200:
        raise GmailError(f"Token exchange failed: HTTP {r.status_code}: {r.text[:300]}")
    tok = r.json()
    if not tok.get("refresh_token"):
        raise GmailError(
            "Google returned no refresh_token. Revoke the app's access at "
            "https://myaccount.google.com/permissions and run `auth` again.")

    config.GMAIL_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.GMAIL_TOKEN_PATH.write_text(json.dumps({
        "refresh_token": tok["refresh_token"],
        "scope": tok.get("scope", config.GMAIL_SCOPE),
        "obtained_at": int(time.time()),
    }, indent=2), encoding="utf-8")
    print(f"✅ Authorized. Refresh token saved to {config.GMAIL_TOKEN_PATH}")


def _refresh_token() -> str:
    if not config.GMAIL_TOKEN_PATH.exists():
        raise GmailError(
            "Not authorized yet. Run `python -m pipeline.gmail_client auth` once.")
    data = json.loads(config.GMAIL_TOKEN_PATH.read_text(encoding="utf-8"))
    rt = data.get("refresh_token")
    if not rt:
        raise GmailError(f"No refresh_token in {config.GMAIL_TOKEN_PATH}; re-run `auth`.")
    return rt


def _access_token() -> str:
    """Return a valid access token, refreshing (and caching) as needed."""
    global _ACCESS
    token, expiry = _ACCESS
    if token and time.time() < expiry - 60:
        return token
    client_id, client_secret = config.require_gmail_creds()
    r = requests.post(TOKEN_ENDPOINT, data={
        "refresh_token": _refresh_token(),
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        raise GmailError(f"Token refresh failed: HTTP {r.status_code}: {r.text[:300]}")
    tok = r.json()
    _ACCESS = (tok["access_token"], time.time() + int(tok.get("expires_in", 3600)))
    return _ACCESS[0]


# --------------------------------------------------------------------------- #
# Draft creation
# --------------------------------------------------------------------------- #
def _build_mime(to: str, subject: str, text: str, html: str,
                image_path: str | None) -> bytes:
    """Assemble a multipart/related message with an inline whiteboard image.

    Structure:
      related
        ├─ alternative ( text/plain , text/html )
        └─ image/png  (Content-ID: <whiteboard>, inline)
    The HTML references the image via `src="cid:whiteboard"`.
    """
    root = MIMEMultipart("related")
    root["To"] = to
    root["From"] = config.MOOO_FROM
    root["Subject"] = subject

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text or "", "plain", "utf-8"))
    alt.attach(MIMEText(html or "", "html", "utf-8"))
    root.attach(alt)

    if image_path and Path(image_path).exists():
        img = MIMEImage(Path(image_path).read_bytes(), _subtype="png")
        img.add_header("Content-ID", "<whiteboard>")
        img.add_header("Content-Disposition", "inline", filename="whiteboard.png")
        root.attach(img)

    return root.as_bytes()


def create_draft(to: str, subject: str, text: str, html: str,
                 image_path: str | None = None, *, max_retries: int = 3) -> str:
    """Create a Gmail draft in MOOO_FROM's mailbox. Returns the draft id."""
    raw = base64.urlsafe_b64encode(
        _build_mime(to, subject, text, html, image_path)).decode("ascii")
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(
                DRAFTS_ENDPOINT,
                headers={"Authorization": f"Bearer {_access_token()}",
                         "Content-Type": "application/json"},
                json={"message": {"raw": raw}},
                timeout=60,
            )
            if r.status_code in (200, 201):
                return r.json().get("id", "")
            if r.status_code in (429, 500, 502, 503, 504):
                last = GmailError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                raise GmailError(f"HTTP {r.status_code}: {r.text[:400]}")
        except (requests.RequestException, GmailError) as exc:
            last = exc
        time.sleep(min(2 ** attempt, 15))
    raise GmailError(f"Gmail draft failed after {max_retries} attempts: {last}")


def create_draft_from_package(out_dir: Path) -> str:
    """Read an `outbox/<slug>/email.json` package and create its Gmail draft."""
    pkg = json.loads((Path(out_dir) / "email.json").read_text(encoding="utf-8"))
    return create_draft(
        to=pkg["to"],
        subject=pkg["subject"],
        text=pkg.get("text", ""),
        html=pkg.get("html", ""),
        image_path=pkg.get("image"),
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_drafts(slugs: list[str]) -> int:
    dirs = ([config.OUTBOX_DIR / s for s in slugs] if slugs
            else sorted(p.parent for p in config.OUTBOX_DIR.glob("*/email.json")))
    if not dirs:
        print("No email packages found in outbox/. Run the funnel first.")
        return 1
    ok = 0
    for d in dirs:
        if not (d / "email.json").exists():
            print(f"  ⚠️  no email.json in {d}")
            continue
        try:
            draft_id = create_draft_from_package(d)
            print(f"  ✉️  draft created for {d.name}  (id={draft_id})")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ {d.name}: {exc}")
    print(f"\n{ok}/{len(dirs)} draft(s) created in {config.MOOO_FROM}.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "auth":
        authorize()
        return 0
    if cmd == "drafts":
        return _cmd_drafts(argv[1:])
    print(__doc__)
    return 0 if cmd in ("", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main())
