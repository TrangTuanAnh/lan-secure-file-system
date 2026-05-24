"""Frontend-only dashboard settings persistence."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_DIR = PROJECT_ROOT / "config"
SETTINGS_FILE = SETTINGS_DIR / "app_settings.json"

DEFAULT_APP_SETTINGS: dict[str, Any] = {
    "appearance": {
        "font_size": "Medium",
        "reduce_glow_effects": False,
        "reduce_animations": False,
        "compact_layout": False,
    },
    "security": {
        "confirm_before_deleting_files": True,
        "warn_before_downloading_unscanned_files": True,
        "auto_logout": "Never",
        "hide_user_id_in_profile_by_default": False,
    },
}


def _deep_merge_settings(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


class AppSettingsStore:
    """Simple JSON-backed settings store for dashboard preferences."""

    @classmethod
    def load(cls) -> dict[str, Any]:
        if not SETTINGS_FILE.exists():
            cls.save(DEFAULT_APP_SETTINGS)
            return deepcopy(DEFAULT_APP_SETTINGS)
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Settings file must contain a JSON object.")
            return _deep_merge_settings(DEFAULT_APP_SETTINGS, raw)
        except Exception:
            cls.save(DEFAULT_APP_SETTINGS)
            return deepcopy(DEFAULT_APP_SETTINGS)

    @classmethod
    def save(cls, settings: dict[str, Any]) -> None:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        normalized = _deep_merge_settings(DEFAULT_APP_SETTINGS, settings)
        SETTINGS_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


__all__ = ["AppSettingsStore", "DEFAULT_APP_SETTINGS", "SETTINGS_FILE"]
