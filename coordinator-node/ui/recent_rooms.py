"""Frontend-only recent room persistence for dashboard quick access."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui.room_data import normalize_room_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECENT_ROOMS_DIR = PROJECT_ROOT / "config"
RECENT_ROOMS_FILE = RECENT_ROOMS_DIR / "recent_rooms.json"


def _room_id(room: dict[str, Any]) -> str:
    return str(room.get("room_id") or room.get("roomId") or room.get("id") or "").strip()


def _room_name(room: dict[str, Any]) -> str:
    return str(room.get("room_name") or room.get("roomName") or room.get("name") or "Untitled Room").strip()


def _user_cache_key(user_id: str = "", username: str = "") -> str:
    subject = (user_id or username).strip()
    return f"recent_room_{subject}" if subject else "recent_room_anonymous"


def _normalize_recent_room(room: dict[str, Any], opened_at: str | None = None) -> dict[str, Any]:
    normalized = normalize_room_payload(room)
    return {
        "room_id": _room_id(normalized),
        "room_name": _room_name(normalized),
        "member_count": normalized.get("member_count", 0),
        "file_count": normalized.get("file_count", 0),
        "role": str(normalized.get("role") or "").strip(),
        "summary": normalized.get("summary") or "",
        "last_activity": normalized.get("last_activity") or "",
        "last_opened_at": opened_at or str(room.get("last_opened_at") or ""),
    }


class RecentRoomsStore:
    """Small JSON store that keeps the latest opened room per user on this client."""

    @classmethod
    def _load_all(cls) -> dict[str, dict[str, Any]]:
        if not RECENT_ROOMS_FILE.exists():
            cls._save_all({})
            return {}
        try:
            raw = json.loads(RECENT_ROOMS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                cls._save_all({})
                return {}
            if not isinstance(raw, dict):
                raise ValueError("recent_rooms.json must contain an object.")
            normalized: dict[str, dict[str, Any]] = {}
            for key, value in raw.items():
                if isinstance(key, str) and isinstance(value, dict) and _room_id(value):
                    normalized[key] = _normalize_recent_room(value)
            if normalized != raw:
                cls._save_all(normalized)
            return normalized
        except Exception:
            cls._save_all({})
            return {}

    @classmethod
    def _save_all(cls, payload: dict[str, dict[str, Any]]) -> None:
        RECENT_ROOMS_DIR.mkdir(parents=True, exist_ok=True)
        RECENT_ROOMS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, user_id: str = "", username: str = "") -> list[dict[str, Any]]:
        room = cls.load_one(user_id=user_id, username=username)
        return [room] if room else []

    @classmethod
    def load_one(cls, user_id: str = "", username: str = "") -> dict[str, Any] | None:
        cache_key = _user_cache_key(user_id=user_id, username=username)
        room = cls._load_all().get(cache_key)
        if not room or not _room_id(room):
            return None
        return _normalize_recent_room(room)

    @classmethod
    def record_opened(cls, room: dict[str, Any], user_id: str = "", username: str = "") -> list[dict[str, Any]]:
        room_id = _room_id(room)
        if not room_id:
            return cls.load(user_id=user_id, username=username)

        payload = cls._load_all()
        payload[_user_cache_key(user_id=user_id, username=username)] = _normalize_recent_room(
            room,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        cls._save_all(payload)
        return cls.load(user_id=user_id, username=username)

    @classmethod
    def sync_with_valid_rooms(
        cls,
        valid_rooms: list[dict[str, Any]],
        user_id: str = "",
        username: str = "",
    ) -> list[dict[str, Any]]:
        valid_map = {
            _room_id(room): _normalize_recent_room(room)
            for room in valid_rooms
            if _room_id(room)
        }
        payload = cls._load_all()
        cache_key = _user_cache_key(user_id=user_id, username=username)
        current = payload.get(cache_key)
        if not current:
            return []

        room_id = _room_id(current)
        if not room_id or room_id not in valid_map:
            payload.pop(cache_key, None)
            cls._save_all(payload)
            return []

        payload[cache_key] = {
            **valid_map[room_id],
            "last_opened_at": str(current.get("last_opened_at") or ""),
        }
        cls._save_all(payload)
        return cls.load(user_id=user_id, username=username)

    @classmethod
    def clear_recent_rooms_cache(cls, user_id: str = "", username: str = "") -> None:
        payload = cls._load_all()
        payload.pop(_user_cache_key(user_id=user_id, username=username), None)
        cls._save_all(payload)


__all__ = ["RecentRoomsStore", "RECENT_ROOMS_FILE"]
