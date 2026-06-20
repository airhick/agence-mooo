"""Resumable state: track which businesses were already processed."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config

_LOCK = threading.Lock()


def _path() -> Path:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    return config.STATE_DIR / "processed.jsonl"


def load_done() -> set[str]:
    """Return the set of keys (place_id|slug) already processed successfully."""
    p = _path()
    if not p.exists():
        return set()
    done: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("status") == "ok":
                done.add(rec["key"])
        except json.JSONDecodeError:
            continue
    return done


def record(key: str, result: dict) -> None:
    rec = {"key": key, **result}
    with _LOCK:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
