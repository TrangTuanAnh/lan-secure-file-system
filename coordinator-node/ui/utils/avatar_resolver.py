"""Resolve and render deterministic dashboard avatar assets."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AVATAR_ROOT = PROJECT_ROOT / "assets" / "avatar"
ADMIN_AVATAR = AVATAR_ROOT / "admin" / "admin.svg"
USER_AVATAR_DIR = AVATAR_ROOT / "user"


def _is_admin_role(global_role: str) -> bool:
    normalized = str(global_role or "").strip().upper()
    return normalized in {"ADMIN", "ADMINISTRATOR"}


def resolve_avatar_path(username: str, user_id: Optional[str] = None, global_role: str = "USER") -> Optional[Path]:
    """Return the stable avatar SVG path for a user profile."""
    if _is_admin_role(global_role) and ADMIN_AVATAR.exists():
        return ADMIN_AVATAR

    user_avatars = sorted(USER_AVATAR_DIR.glob("*.svg"), key=lambda path: path.name.lower())
    if not user_avatars:
        return ADMIN_AVATAR if ADMIN_AVATAR.exists() else None

    stable_key = str(user_id or username or "anonymous-user").strip().lower()
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(user_avatars)
    return user_avatars[index]


def render_svg_avatar(svg_path: Optional[Path], size: QSize) -> Optional[QPixmap]:
    """Render an SVG avatar into a circular pixmap using Qt's SVG renderer."""
    if svg_path is None or not svg_path.exists():
        return None

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        return None

    side = min(size.width(), size.height())
    if side <= 0:
        return None

    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.HighQualityAntialiasing, True)

    # Create circular clipping path
    clip_path = QPainterPath()
    clip_path.addEllipse(QRectF(0.5, 0.5, side - 1, side - 1))
    painter.setClipPath(clip_path)

    default_size = renderer.defaultSize()
    if default_size.isValid() and default_size.width() > 0 and default_size.height() > 0:
        source_ratio = default_size.width() / default_size.height()
        target_ratio = 1.0
        if source_ratio > target_ratio:
            target_width = side
            target_height = side / source_ratio
        else:
            target_height = side
            target_width = side * source_ratio
        target_rect = QRectF(
            (side - target_width) / 2,
            (side - target_height) / 2,
            target_width,
            target_height,
        )
    else:
        target_rect = QRectF(0, 0, side, side)

    renderer.render(painter, target_rect)
    painter.end()
    
    return pixmap


__all__ = ["resolve_avatar_path", "render_svg_avatar"]
