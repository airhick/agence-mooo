"""Generate brand imagery for the Agence Mooo landing page via OpenAI gpt-image-1.

Every image is generated from the brand logo (logomooo.png) used as a *reference*
through the image-edits endpoint, so the whole site shares the cute, soft 3D
"clay" cow universe of the logo.

Resumable: skips any image already on disk. Saves PNGs to ./assets/.
Run a single image first to validate:  python tools/gen_images.py hero

Usage:
    python tools/gen_images.py            # generate all missing images
    python tools/gen_images.py hero       # generate just one (by key)
    python tools/gen_images.py --force    # regenerate everything
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
REFERENCE = ROOT / "logomooo.png"          # the cow logo drives the whole mood
ENDPOINT = "https://api.openai.com/v1/images/edits"
MODEL = "gpt-image-1"

# Shared art direction so every image feels like one cohesive brand world,
# built around the soft 3D "claymation" cow logo.
STYLE = (
    "Match the exact art style of the reference image: cute, soft, rounded 3D "
    "claymation / matte clay render, smooth tactile surfaces, gentle soft "
    "studio lighting with soft shadows. Brand palette: warm cream, soft "
    "dusty-pink (#f3c0b8), charcoal black-and-white cow spots, ivory. Friendly, "
    "premium, playful and calm. Clean and minimal with generous negative space. "
    "Absolutely NO text, NO words, NO logos, NO watermarks, NO letters anywhere."
)

LANDSCAPE = "1536x1024"
SQUARE = "1024x1024"
PORTRAIT = "1024x1536"

# key -> (prompt, size, quality)
IMAGES: dict[str, tuple[str, str, str]] = {
    "hero": (
        "A dreamy, premium hero scene in the same soft 3D clay style as the "
        "reference: the cute black-and-white clay cow mascot from the reference, "
        "calm and friendly, floating gently among soft rounded clay clouds and "
        "smooth pastel shapes, warm cream and dusty-pink atmosphere, soft depth "
        "and bokeh, cinematic but adorable. " + STYLE,
        LANDSCAPE, "high",
    ),
    "hero-reveal": (
        "Macro abstract of soft rounded clay shapes and gentle pastel light, "
        "cream and dusty-pink, smooth tactile blobs and soft bokeh, dreamy and "
        "warm, in the same clay render style as the reference. " + STYLE,
        LANDSCAPE, "high",
    ),
    "vision": (
        "The cute clay cow mascot from the reference happily looking at a "
        "floating soft-rounded clay screen showing a minimal elegant website "
        "(no readable text), warm cream studio, soft pink glow, premium and "
        "charming, vertical composition. " + STYLE,
        PORTRAIT, "high",
    ),
    "show-1": (
        "A floating soft clay screen showing an elegant minimal restaurant "
        "website (no readable text), the cute clay cow peeking beside it, warm "
        "cream backdrop with dusty-pink accents, adorable premium feel. " + STYLE,
        SQUARE, "medium",
    ),
    "show-2": (
        "A floating soft clay screen showing a refined boutique / shop website "
        "(no readable text), the cute clay cow beside it, soft pink and cream "
        "tones, charming minimal layout. " + STYLE,
        SQUARE, "medium",
    ),
    "show-3": (
        "A floating soft clay screen showing a modern artisan / craft business "
        "website (no readable text), the cute clay cow beside it, warm cream and "
        "dusty-pink, premium and playful. " + STYLE,
        SQUARE, "medium",
    ),
    "texture-1": (
        "Abstract soft clay gradient field, warm cream to dusty-pink with a few "
        "smooth charcoal cow-spot shapes drifting, gentle and minimal, tactile "
        "matte surfaces. " + STYLE,
        LANDSCAPE, "medium",
    ),
    "texture-2": (
        "Abstract composition of soft rounded clay shapes and gentle cow-spot "
        "patterns, cream, ivory and dusty-pink, smooth shadows, elegant and "
        "calm. " + STYLE,
        LANDSCAPE, "medium",
    ),
}


def load_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        sys.exit("OPENAI_API_KEY not found (env or .env)")
    return key


def generate(key: str, name: str, prompt: str, size: str, quality: str) -> None:
    out = ASSETS / f"{name}.png"
    headers = {"Authorization": f"Bearer {key}"}
    data = {"model": MODEL, "prompt": prompt, "size": size, "quality": quality, "n": "1"}
    for attempt in range(1, 5):
        with REFERENCE.open("rb") as fh:
            files = {"image": (REFERENCE.name, fh, "image/png")}
            r = requests.post(ENDPOINT, headers=headers, data=data, files=files, timeout=300)
        if r.status_code == 200:
            d = r.json()["data"][0]
            b64 = d.get("b64_json")
            if b64:
                out.write_bytes(base64.b64decode(b64))
            else:
                img = requests.get(d["url"], timeout=120)
                out.write_bytes(img.content)
            print(f"  ✓ {out.name}  ({size}, {quality}, {out.stat().st_size//1024} KB)")
            return
        if r.status_code in (429, 500, 502, 503):
            wait = 2 ** attempt
            print(f"  … {r.status_code}, retry in {wait}s")
            time.sleep(wait)
            continue
        sys.exit(f"  ✗ {name}: HTTP {r.status_code}\n{r.text[:600]}")
    sys.exit(f"  ✗ {name}: exhausted retries")


def main(argv: list[str]) -> int:
    ASSETS.mkdir(exist_ok=True)
    if not REFERENCE.exists():
        sys.exit(f"reference logo not found: {REFERENCE}")
    key = load_key()
    force = "--force" in argv
    only = [a for a in argv if not a.startswith("-")]
    keys = only or list(IMAGES)
    for name in keys:
        if name not in IMAGES:
            sys.exit(f"unknown image key: {name} (have: {', '.join(IMAGES)})")
        out = ASSETS / f"{name}.png"
        if out.exists() and not force:
            print(f"  · {out.name} exists, skip")
            continue
        prompt, size, quality = IMAGES[name]
        print(f"→ {name} …")
        generate(key, name, prompt, size, quality)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
