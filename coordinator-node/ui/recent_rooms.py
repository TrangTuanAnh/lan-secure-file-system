"""Frontend-only recent room persistence for dashboard quick access."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECENT_ROOMS_DIR = PROJECT_ROOT / "config"
RECENT_ROOMS_FILE = RECENT_ROOMS_DIR / "recent_rooms.json"
MAX_RECENT_ROOMS = 3


def _room_id(room: dict[str, Any]) -> str:
    return str(room.get("room_id") or room.get("roomId") or room.get("id") or "").strip()


def _room_name(room: dict[str, Any]) -> str:
    return str(room.get("room_name") or room.get("roomName") or room.get("name") or "Untitled Room").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_recent_room(room: dict[str, Any], opened_at: str | None = None) -> dict[str, Any]:
    return {
        "room_id": _room_id(room),
        "room_name": _room_name(room),
        "member_count": _safe_int(room.get("member_count") or room.get("memberCount") or room.get("membersCount")),
        "file_count": _safe_int(room.get("file_count") or room.get("fileCount")),
        "role": str(room.get("role") or room.get("memberRole") or room.get("myRole") or "").strip(),
        "last_opened_at": opened_at or str(room.get("last_opened_at") or ""),
    }


class RecentRoomsStore:
    """Small JSON store that keeps the latest opened rooms on this client."""

    @classmethod
    def load(cls) -> list[dict[str, Any]]:
        if not RECENT_ROOMS_FILE.exists():
            cls.save([])
            return []
        try:
            raw = json.loads(RECENT_ROOMS_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("recent_rooms.json must contain a list.")
            rooms = [_normalize_recent_room(item) for item in raw if isinstance(item, dict) and _room_id(item)]
            return cls._sorted_limited(rooms)
        except Exception:
            cls.save([])
            return []

    @classmethod
    def save(cls, rooms: list[dict[str, Any]]) -> None:
        RECENT_ROOMS_DIR.mkdir(parents=True, exist_ok=True)
        normalized = cls._sorted_limited([_normalize_recent_room(room) for room in rooms if _room_id(room)])
        RECENT_ROOMS_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    @classmethod
    def record_opened(cls, room: dict[str, Any]) -> list[dict[str, Any]]:
        room_id = _room_id(room)
        if not room_id:
            return cls.load()

        opened_at = datetime.now(timezone.utc).isoformat()
        current = [item for item in cls.load() if _room_id(item) != room_id]
        current.append(_normalize_recent_room(room, opened_at=opened_at))
        cls.save(current)
        return cls.load()

    @classmethod
    def sync_with_valid_rooms(cls, valid_rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Keep only recent rooms that still exist in the latest backend room list.

        Existing ordering by ``last_opened_at`` is preserved, while display
        metadata is refreshed from the latest backend payload.
        """
        valid_map = {
            _room_id(room): _normalize_recent_room(room)
            for room in valid_rooms
            if _room_id(room)
        }
        synced: list[dict[str, Any]] = []
        for room in cls.load():
            room_id = _room_id(room)
            if not room_id or room_id not in valid_map:
                continue
            refreshed = {
                **valid_map[room_id],
                "last_opened_at": str(room.get("last_opened_at") or ""),
            }
            synced.append(refreshed)
        cls.save(synced)
        return cls.load()

    @classmethod
    def clear_recent_rooms_cache(cls) -> None:
        """Clear only the recent-room cache without touching other settings."""
        cls.save([])

    @staticmethod
    def _sorted_limited(rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rooms,
            key=lambda room: str(room.get("last_opened_at") or ""),
            reverse=True,
        )[:MAX_RECENT_ROOMS]


__all__ = ["RecentRoomsStore", "RECENT_ROOMS_FILE"]
