from __future__ import annotations
import json, os
from typing import Optional
from app.models import Settings

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "db", "settings.json")

DEFAULT = Settings().model_dump()

def ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT, f, ensure_ascii=False, indent=2)

def load_settings() -> Settings:
    ensure_db()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Settings(**data)

def save_settings(s: Settings) -> None:
    ensure_db()
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(s.model_dump(), f, ensure_ascii=False, indent=2)
