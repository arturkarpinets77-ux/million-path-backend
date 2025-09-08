# app/core/storage.py
from __future__ import annotations
import json, os, time
from typing import Any, Tuple

BD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "BD")
BD_DIR = os.path.abspath(BD_DIR)
os.makedirs(BD_DIR, exist_ok=True)

def _path(name: str) -> str:
    return os.path.join(BD_DIR, name)

def load_json(name: str, default: Any) -> Any:
    p = _path(name)
    if not os.path.exists(p):
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(name: str, data: Any) -> None:
    p = _path(name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def now_ts() -> float:
    return time.time()
