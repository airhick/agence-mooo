"""Generate imagery for the Agence Mooo landing page via OpenAI gpt-image-2.

Two families of images:

1. BRAND images (hero, textures) — generated from the brand logo (logomooo.png)
   used as a *reference* through the image-edits endpoint, so they share the
   cute, soft 3D "clay" cow universe of the logo.

2. SHOWCASE images (show-1/2/3, vision) — clean, realistic screenshots of
   *professional websites*, each with a different industry and a distinct,
   varied UI, so a prospective client can project themselves onto the result.
   These are generated text-to-image (no clay reference) for true-to-life UIs.

Resumable: skips any image already on disk. Saves PNGs to ./assets/.
Run a single image first to validate:  python tools/gen_images.py show-1

Usage:
    python tools/gen_images.py            # generate all missing images
    python tools/gen_images.py show-1     # generate just one (by key)
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
REFERENCE = ROOT / "logomooo.png"          # the cow logo drives the brand mood
EDITS_ENDPOINT = "https://api.openai.com/v1/images/edits"
GEN_ENDPOINT = "https://api.openai.com/v1/images/generations"
MODEL = "gpt-image-2"

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

# --- BRAND clay images (generated with the logo as reference) ---------------
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

# --- SHOWCASE website screenshots (text-to-image, no clay reference) ---------
# Clean, realistic, *varied* professional website UIs so a prospective client
# can picture their own future site. Each is a different industry AND a
# distinctly different layout / design language.
SHOT_STYLE = (
    "Ultra-realistic, high-fidelity screenshot of a professional website "
    "homepage, as if captured directly from a screen. Pixel-perfect modern web "
    "design by a top studio: crisp clean typography, real-looking legible "
    "interface text, a clear navigation bar, well-balanced spacing and a "
    "tasteful call-to-action button. Straight-on flat view filling the whole "
    "frame, no browser chrome, no window borders, no mouse cursor, no device "
    "frame, sharp and photorealistic. No watermark."
)

SHOWCASE: dict[str, tuple[str, str, str]] = {
    # Elegant restaurant — warm editorial, big food photography
    "show-1": (
        "Homepage of an elegant neighbourhood restaurant. Warm editorial layout: "
        "a large full-width appetising plated-food photograph as the hero, a "
        "refined serif headline overlaid, a 'Réserver' reservation button, a "
        "slim top menu, and a row of dish cards below. Warm cream, terracotta "
        "and charcoal palette, generous white space. " + SHOT_STYLE,
        LANDSCAPE, "high",
    ),
    # Fashion boutique e-commerce — minimal product grid
    "show-2": (
        "Homepage of a chic fashion boutique online shop. Minimalist editorial "
        "e-commerce design: a clean responsive grid of product cards with soft "
        "pastel studio product photos, thin sans-serif typography, small price "
        "tags, a slim navigation bar with a cart icon, lots of negative space. "
        "Soft dusty-pink, ivory and charcoal palette. " + SHOT_STYLE,
        LANDSCAPE, "high",
    ),
    # Artisan coffee roaster — bold, expressive, asymmetric
    "show-3": (
        "Homepage of an artisan coffee roaster. Bold modern design: oversized "
        "expressive display typography, a striking hero photo of a coffee cup "
        "and roasted beans, a dynamic asymmetric layout, a 'Boutique' shop "
        "button, sticky nav. Warm earthy browns, deep green and cream palette. "
        + SHOT_STYLE,
        LANDSCAPE, "high",
    ),
    # Wellness / yoga studio shown on a phone — different format for variety
    "vision": (
        "A modern responsive website homepage for a boutique wellness and yoga "
        "studio, displayed on a smartphone screen, vertical mobile UI. Serene "
        "full-bleed calm photo hero, soft sage-green and cream palette, rounded "
        "buttons, clean class-schedule cards, a tidy bottom navigation bar. "
        "Elegant, airy and premium. " + SHOT_STYLE,
        PORTRAIT, "high",
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


def _save(out: Path, payload: dict, size: str, quality: str) -> None:
    d = payload["data"][0]
    b64 = d.get("b64_json")
    if b64:
        out.write_bytes(base64.b64decode(b64))
    else:
        img = requests.get(d["url"], timeout=120)
        out.write_bytes(img.content)
    print(f"  ✓ {out.name}  ({size}, {quality}, {out.stat().st_size//1024} KB)")


def generate(key: str, name: str, prompt: str, size: str, quality: str,
             reference: bool) -> None:
    """reference=True -> clay edit from the logo; False -> plain text-to-image."""
    out = ASSETS / f"{name}.png"
    headers = {"Authorization": f"Bearer {key}"}
    data = {"model": MODEL, "prompt": prompt, "size": size, "quality": quality, "n": 1}
    for attempt in range(1, 5):
        if reference:
            with REFERENCE.open("rb") as fh:
                files = {"image": (REFERENCE.name, fh, "image/png")}
                r = requests.post(EDITS_ENDPOINT, headers=headers, data=data,
                                  files=files, timeout=300)
        else:
            r = requests.post(GEN_ENDPOINT, headers={**headers,
                              "Content-Type": "application/json"},
                              json=data, timeout=300)
        if r.status_code == 200:
            _save(out, r.json(), size, quality)
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
    keys = only or (list(IMAGES) + list(SHOWCASE))
    for name in keys:
        if name in IMAGES:
            prompt, size, quality = IMAGES[name]
            reference = True
        elif name in SHOWCASE:
            prompt, size, quality = SHOWCASE[name]
            reference = False
        else:
            avail = ", ".join(list(IMAGES) + list(SHOWCASE))
            sys.exit(f"unknown image key: {name} (have: {avail})")
        out = ASSETS / f"{name}.png"
        if out.exists() and not force:
            print(f"  · {out.name} exists, skip")
            continue
        print(f"→ {name} …")
        generate(key, name, prompt, size, quality, reference)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
