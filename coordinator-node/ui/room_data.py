"""Shared room payload normalization helpers for dashboard pages."""

from __future__ import annotations

from typing import Any, Iterable


ROOM_MEMBER_COUNT_KEYS = ("memberCount", "membersCount", "member_count", "members_count")
ROOM_FILE_COUNT_KEYS = ("fileCount", "filesCount", "file_count", "files_count")
ROOM_ROLE_KEYS = (
    "current_user_role",
    "currentUserRole",
    "userRole",
    "memberRole",
    "myRole",
    "role",
)


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def resolve_count(payload: dict[str, Any], keys: Iterable[str]) -> tuple[int, bool]:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return safe_int(payload.get(key)), True
    return 0, False


def normalize_room_role(value: Any, default: str = "VIEWER") -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"OWNER", "MEMBER", "VIEWER"}:
        return normalized
    return default


def resolve_room_role(room: dict[str, Any], default: str = "VIEWER") -> str:
    membership_payload = (
        room.get("current_user_membership")
        or room.get("currentUserMembership")
        or room.get("membership")
    )
    if isinstance(membership_payload, dict):
        return normalize_room_role(
            membership_payload.get("role")
            or membership_payload.get("roomRole")
            or membership_payload.get("userRole"),
            default=default,
        )
    if membership_payload is not None:
        resolved = normalize_room_role(membership_payload, default="")
        if resolved:
            return resolved

    for key in ROOM_ROLE_KEYS:
        if room.get(key) is not None:
            return normalize_room_role(room.get(key), default=default)
    return default


def infer_room_role_from_members(
    members: list[dict[str, Any]],
    *,
    user_id: str = "",
    username: str = "",
    default: str = "VIEWER",
) -> str:
    normalized_user_id = str(user_id or "").strip()
    normalized_username = str(username or "").strip().lower()

    for member in members:
        member_user_id = str(member.get("userId") or member.get("user_id") or member.get("id") or "").strip()
        member_username = str(member.get("username") or "").strip().lower()
        if normalized_user_id and member_user_id and member_user_id == normalized_user_id:
            return normalize_room_role(member.get("role"), default=default)
        if normalized_username and member_username and member_username == normalized_username:
            return normalize_room_role(member.get("role"), default=default)
    return default


def normalize_room_payload(
    room: dict[str, Any],
    *,
    fallback_member_count: int | None = None,
    fallback_file_count: int | None = None,
) -> dict[str, Any]:
    member_count, has_member_count = resolve_count(room, ROOM_MEMBER_COUNT_KEYS)
    file_count, has_file_count = resolve_count(room, ROOM_FILE_COUNT_KEYS)

    if not has_member_count and fallback_member_count is not None:
        member_count = safe_int(fallback_member_count)
    if not has_file_count and fallback_file_count is not None:
        file_count = safe_int(fallback_file_count)

    return {
        "room_id": room.get("room_id") or room.get("id") or room.get("roomId") or "",
        "room_name": room.get("room_name") or room.get("name") or room.get("roomName") or "Untitled Room",
        "role": resolve_room_role(room),
        "member_count": member_count,
        "file_count": file_count,
        "summary": room.get("summary")
        or room.get("description")
        or "Secure collaborative room with encrypted document access.",
        "last_activity": room.get("last_activity")
        or room.get("lastActivity")
        or room.get("updatedAt")
        or "No recent activity recorded.",
    }
