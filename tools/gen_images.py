"""Generate brand imagery for the Agence Mooo landing page via OpenAI gpt-image-1.

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
ENDPOINT = "https://api.openai.com/v1/images/generations"
MODEL = "gpt-image-1"

# Shared art direction so every image feels like one cohesive brand world.
STYLE = (
    "Cinematic, premium, editorial. Deep near-black navy background with soft "
    "electric cyan (#bfeeff) and cool blue light. Glass, light, and depth, "
    "subtle film grain, elegant negative space. Absolutely NO text, NO words, "
    "NO logos, NO watermarks, NO letters anywhere in the image."
)

# key -> (prompt, size, quality)
LANDSCAPE = "1536x1024"
SQUARE = "1024x1024"
PORTRAIT = "1024x1536"

IMAGES: dict[str, tuple[str, str, str]] = {
    "hero": (
        "A sleek modern website glowing on a floating pane of glass in a dark "
        "studio, soft cyan rim light, reflections, sense of craft and calm "
        "luxury, abstract and atmospheric. " + STYLE,
        LANDSCAPE, "high",
    ),
    "hero-reveal": (
        "Macro abstract of liquid light and flowing glass ribbons in the dark, "
        "electric cyan highlights, dreamy bokeh, futuristic and refined. " + STYLE,
        LANDSCAPE, "high",
    ),
    "vision": (
        "A designer's dark desk seen from above, a single screen showing an "
        "elegant minimal website, warm-cool cyan glow, moody cinematic studio, "
        "premium craft atmosphere. " + STYLE,
        PORTRAIT, "high",
    ),
    "show-1": (
        "An elegant restaurant website displayed on a floating glass screen in "
        "the dark, cyan accent light, minimal premium UI feeling, no readable "
        "text. " + STYLE,
        SQUARE, "medium",
    ),
    "show-2": (
        "A refined boutique / shop website on a floating dark glass panel, soft "
        "blue light, sophisticated minimal layout, no readable text. " + STYLE,
        SQUARE, "medium",
    ),
    "show-3": (
        "A modern artisan / craft business website on a glowing dark glass "
        "screen, cyan rim light, premium minimal feel, no readable text. " + STYLE,
        SQUARE, "medium",
    ),
    "texture-1": (
        "Abstract dark gradient mesh, deep navy to black with a single soft "
        "cyan glow, smooth and atmospheric, minimal. " + STYLE,
        LANDSCAPE, "medium",
    ),
    "texture-2": (
        "Abstract architectural glass and light forms in the dark, cool blue "
        "and cyan, elegant geometry, depth and shadow. " + STYLE,
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
    payload = {
        "model": MODEL, "prompt": prompt, "size": size,
        "quality": quality, "n": 1,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(1, 5):
        r = requests.post(ENDPOINT, json=payload, headers=headers, timeout=300)
        if r.status_code == 200:
            data = r.json()["data"][0]
            b64 = data.get("b64_json")
            if b64:
                out.write_bytes(base64.b64decode(b64))
            else:  # some responses return a url
                img = requests.get(data["url"], timeout=120)
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
