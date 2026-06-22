"""Minimal OpenAI client (requests-based) for the outreach step.

Two calls only:
- `chat()`           — gpt-4o writes the short French outreach email.
- `image_edit()`     — gpt-image-2 edits the blank whiteboard photo to handwrite
                       a personalized message; returns raw PNG bytes.

Mirrors the retry/backoff style of `pipeline.deepseek` and `tools/gen_images.py`.
"""
from __future__ import annotations

import base64
import time

import requests

from . import config


class OpenAIError(RuntimeError):
    pass


def chat(messages: list[dict], *, model: str | None = None,
         temperature: float = 0.7, max_tokens: int = 800,
         max_retries: int = 4, timeout: int = 120) -> str:
    """OpenAI chat completion -> assistant text. Retries on 429/5xx."""
    key = config.require_openai_key()
    url = f"{config.OPENAI_BASE_URL}/chat/completions"
    payload = {
        "model": model or config.OPENAI_MAIL_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return (r.json()["choices"][0]["message"]["content"] or "").strip()
            if r.status_code in (429, 500, 502, 503, 504):
                last = OpenAIError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                raise OpenAIError(f"HTTP {r.status_code}: {r.text[:400]}")
        except (requests.RequestException, OpenAIError) as exc:
            last = exc
        time.sleep(min(2 ** attempt, 20))
    raise OpenAIError(f"OpenAI chat failed after {max_retries} attempts: {last}")


def image_edit(image_path, prompt: str, *, model: str | None = None,
               size: str = "1024x1024", max_retries: int = 4,
               timeout: int = 300) -> bytes:
    """Edit `image_path` with gpt-image-2 and return the resulting PNG bytes."""
    key = config.require_openai_key()
    url = f"{config.OPENAI_BASE_URL}/images/edits"
    headers = {"Authorization": f"Bearer {key}"}
    data = {"model": model or config.OPENAI_IMAGE_MODEL, "prompt": prompt,
            "size": size, "n": 1}
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            with open(image_path, "rb") as fh:
                files = {"image": ("whiteboard.png", fh, "image/png")}
                r = requests.post(url, headers=headers, data=data, files=files,
                                  timeout=timeout)
            if r.status_code == 200:
                d = r.json()["data"][0]
                if d.get("b64_json"):
                    return base64.b64decode(d["b64_json"])
                return requests.get(d["url"], timeout=120).content
            if r.status_code in (429, 500, 502, 503, 504):
                last = OpenAIError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                raise OpenAIError(f"HTTP {r.status_code}: {r.text[:400]}")
        except (requests.RequestException, OpenAIError) as exc:
            last = exc
        time.sleep(min(2 ** attempt, 20))
    raise OpenAIError(f"OpenAI image edit failed after {max_retries} attempts: {last}")
