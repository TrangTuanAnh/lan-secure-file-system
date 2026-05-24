"""Reusable premium button for the desktop security UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    Property,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.fonts import app_font, ui_font_family


@dataclass(frozen=True)
class CyberPalette:
    """Shared colors for all reusable widgets."""

    background: str = "#0f0f1e"
    surface: str = "#1a1a2e"
    surface_alt: str = "#222239"
    border: str = "#2d3352"
    text: str = "#f4fff9"
    text_muted: str = "#8aa39a"
    accent: str = "#00b248"
    accent_alt: str = "#00c853"
    accent_soft: str = "#00e676"
    accent_bright: str = "#00ff95"
    disabled_fill: str = "#171726"
    disabled_text: str = "#5f6d6a"
    error: str = "#ff4d6d"
    error_fill: str = "#32141d"


PALETTE = CyberPalette()


def to_color(value: QColor | str) -> QColor:
    """Normalize user supplied colors."""
    return value if isinstance(value, QColor) else QColor(value)


def with_alpha(color: QColor | str, alpha: int) -> QColor:
    """Return a copy with a custom alpha channel."""
    normalized = QColor(to_color(color))
    normalized.setAlpha(max(0, min(alpha, 255)))
    return normalized


def blend(color_a: QColor | str, color_b: QColor | str, ratio: float) -> QColor:
    """Blend two colors while keeping gradients smooth."""
    ratio = max(0.0, min(ratio, 1.0))
    first = to_color(color_a)
    second = to_color(color_b)
    return QColor(
        int(first.red() + (second.red() - first.red()) * ratio),
        int(first.green() + (second.green() - first.green()) * ratio),
        int(first.blue() + (second.blue() - first.blue()) * ratio),
        int(first.alpha() + (second.alpha() - first.alpha()) * ratio),
    )


class ModernButton(QPushButton):
    """Animated button with subtle glow and loading feedback."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._accent_color = QColor(PALETTE.accent)
        self._accent_color_alt = QColor(PALETTE.accent_alt)
        self._background_color = QColor(PALETTE.surface)
        self._background_color_alt = QColor(PALETTE.surface_alt)
        self._text_color = QColor(PALETTE.text)
        self._radius = 14
        self._hover_progress = 0.0
        self._press_progress = 0.0
        self._loading = False
        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(22)
        self._spinner_timer.timeout.connect(self._advance_spinner)
        self._hover_animation = self._build_animation(b"hoverProgress", 190)
        self._press_animation = self._build_animation(b"pressProgress", 110)
        self._cached_text = text

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFont(app_font(10, QFont.DemiBold))
        self.setCheckable(False)
        self.setFlat(True)
        self.set_button_style()

    def _build_animation(self, prop_name: bytes, duration: int) -> QPropertyAnimation:
        animation = QPropertyAnimation(self, prop_name, self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        return animation

    def _advance_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 18) % 360
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and not self._loading:
            self._animate(self._hover_animation, self._hover_progress, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate(self._hover_animation, self._hover_progress, 0.0)
        if not self._loading:
            self._animate(self._press_animation, self._press_progress, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled() and not self._loading:
            self._animate(self._press_animation, self._press_progress, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and not self._loading:
            target = 1.0 if self.rect().contains(event.position().toPoint()) else 0.0
            self._animate(self._press_animation, self._press_progress, 0.0)
            self._animate(self._hover_animation, self._hover_progress, target)
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if not self.isEnabled():
            self._animate(self._hover_animation, self._hover_progress, 0.0)
            self._animate(self._press_animation, self._press_progress, 0.0)
        super().changeEvent(event)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(max(hint.height(), 46))
        hint.setWidth(max(hint.width(), 128))
        return hint

    def _animate(self, animation: QPropertyAnimation, start: float, end: float) -> None:
        animation.stop()
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.start()

    def getHoverProgress(self) -> float:
        return self._hover_progress

    def setHoverProgress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(value, 1.0))
        self.update()

    hoverProgress = Property(float, getHoverProgress, setHoverProgress)

    def getPressProgress(self) -> float:
        return self._press_progress

    def setPressProgress(self, value: float) -> None:
        self._press_progress = max(0.0, min(value, 1.0))
        self.update()

    pressProgress = Property(float, getPressProgress, setPressProgress)

    def set_loading(self, is_loading: bool, text: Optional[str] = None) -> None:
        """Toggle loading mode without breaking layout stability."""
        self._loading = is_loading
        if text is not None:
            self._cached_text = text
        if is_loading:
            self.setCursor(Qt.BusyCursor)
            self._spinner_angle = 0
            self._spinner_timer.start()
            self._animate(self._press_animation, self._press_progress, 0.0)
        else:
            self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)
            self._spinner_timer.stop()
        self.update()

    def set_accent_color(self, color: QColor | str) -> None:
        """Apply a different accent while preserving the shared theme."""
        accent = to_color(color)
        self._accent_color = accent
        self._accent_color_alt = blend(accent, QColor(PALETTE.accent_bright), 0.36)
        self.update()

    def set_button_style(
        self,
        *,
        radius: Optional[int] = None,
        background_color: Optional[QColor | str] = None,
        background_alt: Optional[QColor | str] = None,
        text_color: Optional[QColor | str] = None,
    ) -> None:
        """Update reusable visual primitives for variants."""
        if radius is not None:
            self._radius = max(8, radius)
        if background_color is not None:
            self._background_color = to_color(background_color)
        if background_alt is not None:
            self._background_color_alt = to_color(background_alt)
        if text_color is not None:
            self._text_color = to_color(text_color)

        self.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {self._text_color.name()};
                font-family: "{ui_font_family()}";
                padding: 0;
            }}
            QPushButton:disabled {{
                color: {PALETTE.disabled_text};
            }}
            """
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        outer_rect = self.rect().adjusted(2, 2, -2, -2)
        scale_offset = 1.8 * self._press_progress
        button_rect = QRectF(outer_rect).adjusted(
            scale_offset,
            scale_offset,
            -scale_offset,
            -scale_offset,
        )
        path = QPainterPath()
        path.addRoundedRect(button_rect, self._radius, self._radius)

        glow_color = with_alpha(self._accent_color, int(54 + (100 * self._hover_progress)))
        for spread, alpha_ratio in ((14, 0.22), (8, 0.35)):
            painter.setPen(QPen(with_alpha(glow_color, int(255 * alpha_ratio)), spread))
            painter.drawPath(path)

        fill_gradient = QLinearGradient(button_rect.topLeft(), button_rect.bottomRight())
        fill_gradient.setColorAt(0.0, blend(self._background_color, self._accent_color, 0.10 + (0.08 * self._hover_progress)))
        fill_gradient.setColorAt(0.55, blend(self._background_color_alt, self._accent_color_alt, 0.12 + (0.12 * self._hover_progress)))
        fill_gradient.setColorAt(1.0, blend(self._background_color, self._accent_color, 0.05 + (0.14 * self._press_progress)))
        painter.fillPath(path, fill_gradient)

        border_gradient = QLinearGradient(button_rect.topLeft(), button_rect.bottomRight())
        border_gradient.setColorAt(0.0, blend(PALETTE.border, self._accent_color, 0.55 + (0.15 * self._hover_progress)))
        border_gradient.setColorAt(1.0, blend(PALETTE.surface_alt, self._accent_color_alt, 0.30 + (0.25 * self._hover_progress)))
        border_pen = QPen()
        border_pen.setWidthF(1.2)
        border_pen.setBrush(QBrush(border_gradient))
        painter.setPen(border_pen)
        painter.drawPath(path)

        if not self.isEnabled():
            painter.fillPath(path, with_alpha(PALETTE.disabled_fill, 165))

        painter.setPen(self._text_color if self.isEnabled() else QColor(PALETTE.disabled_text))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)

        text_rect = button_rect.adjusted(14, 0, -14, 0)
        if self._loading:
            self._paint_spinner(painter, text_rect)
            text_rect.adjust(18, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignCenter, self._cached_text or self.text())
        else:
            painter.drawText(text_rect, Qt.AlignCenter, self.text())

    def _paint_spinner(self, painter: QPainter, text_rect: QRectF) -> None:
        spinner_size = 14
        cx = text_rect.center().x() - 48
        cy = text_rect.center().y()
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._spinner_angle)
        for index in range(12):
            color = with_alpha(self._accent_color_alt, int(30 + (index * 16)))
            painter.setPen(QPen(color, 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(0, -(spinner_size // 2), 0, -(spinner_size // 2) + 4)
            painter.rotate(30)
        painter.restore()


__all__ = [
    "CyberPalette",
    "ModernButton",
    "PALETTE",
    "app_font",
    "blend",
    "to_color",
    "with_alpha",
]
