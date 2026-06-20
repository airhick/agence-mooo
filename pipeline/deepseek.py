"""DeepSeek chat client (OpenAI-compatible) with retries and usage tracking."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import requests

from . import config


@dataclass
class Usage:
    """Thread-safe accumulator for token usage across the run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


USAGE = Usage()


class DeepSeekError(RuntimeError):
    pass


def chat(
    messages: list[dict],
    *,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    max_retries: int = 5,
    timeout: int = 180,
) -> str:
    """Call DeepSeek chat completions. Returns assistant message content.

    Retries on 429 / 5xx / network errors with exponential backoff.
    """
    api_key = config.require_api_key()
    url = f"{config.DEEPSEEK_BASE_URL}/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                usage = data.get("usage", {}) or {}
                USAGE.add(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
                return data["choices"][0]["message"]["content"] or ""
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = DeepSeekError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                raise DeepSeekError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        except (requests.RequestException, DeepSeekError) as exc:
            last_err = exc
        sleep = min(2 ** attempt, 30)
        time.sleep(sleep)
    raise DeepSeekError(f"DeepSeek failed after {max_retries} attempts: {last_err}")
