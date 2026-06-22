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
from pathlib import Path

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


def describe_images(image_paths, prompt: str, *, model: str | None = None,
                    max_tokens: int = 600, max_retries: int = 3,
                    timeout: int = 120) -> str:
    """gpt-4o vision: describe real photos as text (so a text-only model can use
    them). Returns the assistant text, or "" on any failure (best-effort).

    Used to translate the company's Google Maps photos into a 'visual energy'
    brief — palette, materials, light, mood — that feeds the art direction.
    """
    paths = [Path(p) for p in image_paths if Path(p).exists()]
    if not paths or not config.OPENAI_API_KEY:
        return ""
    key = config.OPENAI_API_KEY
    url = f"{config.OPENAI_BASE_URL}/chat/completions"
    content: list[dict] = [{"type": "text", "text": prompt}]
    for p in paths:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                      "detail": "low"}})
    payload = {
        "model": model or config.OPENAI_MAIL_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return (r.json()["choices"][0]["message"]["content"] or "").strip()
            if r.status_code not in (429, 500, 502, 503, 504):
                return ""   # non-retryable: degrade silently, energy is optional
        except requests.RequestException:
            pass
        time.sleep(min(2 ** attempt, 15))
    return ""


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
