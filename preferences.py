"""Local JSON preferences; configure DATA_DIR to a persistent mount on hosting."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "channel_name": "Preet Sports",
    "language": "Hindi",
    "description_intro": "Welcome to Preet Sports!",
    "subscribe_cta": "Subscribe to Preet Sports for cricket live updates, live score discussions, and match reactions.",
    "default_tags": "Preet Sports, cricket live, live score, Hindi commentary",
    "default_hashtags": "PreetSports CricketLive",
    "default_region": "IN",
    "default_topic": "Cricket",
}


def data_dir() -> Path:
    raw = os.getenv("DATA_DIR", "")
    path = Path(raw).expanduser() if raw else Path(__file__).resolve().parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def preferences_path() -> Path:
    return data_dir() / "preet_preferences.json"


def load_preferences() -> dict[str, Any]:
    result = dict(DEFAULTS)
    path = preferences_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                result.update({key: value for key, value in loaded.items() if key in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass
    return result


def save_preferences(values: dict[str, Any]) -> None:
    cleaned = {key: str(values.get(key, DEFAULTS[key])).strip() for key in DEFAULTS}
    preferences_path().write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
