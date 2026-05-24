"""Reusable dark line edit for the desktop security UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QSizePolicy, QWidget

from ui.fonts import app_font, ui_font_family

from .modern_button import PALETTE, blend, to_color, with_alpha


class ModernLineEdit(QLineEdit):
    """A polished line edit with animated focus and hover states."""

    def __init__(
        self,
        placeholder_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._border_progress = 0.0
        self._focus_glow = 0.0
        self._hover_progress = 0.0
        self._radius = 14
        self._accent_color = QColor(PALETTE.accent_alt)
        self._background_color = QColor(PALETTE.surface)
        self._hover_animation = self._build_animation(b"hoverProgress", 160)
        self._border_animation = self._build_animation(b"borderProgress", 180)
        self._glow_animation = self._build_animation(b"focusGlow", 220)

        self.setPlaceholderText(placeholder_text)
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFont(app_font(10))
        self.setFrame(False)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setTextMargins(18, 0, 18, 0)
        self._apply_base_stylesheet()

    def _build_animation(self, prop_name: bytes, duration: int) -> QPropertyAnimation:
        animation = QPropertyAnimation(self, prop_name, self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        return animation

    def _apply_base_stylesheet(self) -> None:
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
                selection-background-color: {with_alpha(PALETTE.accent_alt, 120).name(QColor.HexArgb)};
                selection-color: {PALETTE.text};
                padding: 0 16px;
            }}
            QLineEdit::placeholder {{
                color: {PALETTE.text_muted};
            }}
            QLineEdit:disabled {{
                color: {PALETTE.disabled_text};
            }}
            """
        )

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(max(hint.height(), 48))
        return hint

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate(self._hover_animation, self._hover_progress, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate(self._hover_animation, self._hover_progress, 0.0)
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._animate(self._border_animation, self._border_progress, 1.0)
        self._animate(self._glow_animation, self._focus_glow, 1.0)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._animate(self._border_animation, self._border_progress, 0.0)
        self._animate(self._glow_animation, self._focus_glow, 0.0)
        super().focusOutEvent(event)

    def _animate(self, animation: QPropertyAnimation, start: float, end: float) -> None:
        animation.stop()
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.start()

    def getBorderProgress(self) -> float:
        return self._border_progress

    def setBorderProgress(self, value: float) -> None:
        self._border_progress = max(0.0, min(value, 1.0))
        self.update()

    borderProgress = Property(float, getBorderProgress, setBorderProgress)

    def getFocusGlow(self) -> float:
        return self._focus_glow

    def setFocusGlow(self, value: float) -> None:
        self._focus_glow = max(0.0, min(value, 1.0))
        self.update()

    focusGlow = Property(float, getFocusGlow, setFocusGlow)

    def getHoverProgress(self) -> float:
        return self._hover_progress

    def setHoverProgress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(value, 1.0))
        self.update()

    hoverProgress = Property(float, getHoverProgress, setHoverProgress)

    def set_accent_color(self, color: QColor | str) -> None:
        self._accent_color = to_color(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        hover_mix = 0.05 + (0.07 * self._hover_progress)
        fill_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill_gradient.setColorAt(0.0, blend(self._background_color, self._accent_color, hover_mix))
        fill_gradient.setColorAt(1.0, blend(PALETTE.surface_alt, self._accent_color, hover_mix * 0.65))
        painter.fillPath(path, fill_gradient)

        if self._focus_glow > 0:
            glow_color = with_alpha(self._accent_color, int(110 * self._focus_glow))
            for width, alpha_scale in ((12, 0.18), (6, 0.28)):
                painter.setPen(QPen(with_alpha(glow_color, int(255 * alpha_scale)), width))
                painter.drawPath(path)

        border_gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        border_gradient.setColorAt(0.0, blend(PALETTE.border, self._accent_color, 0.22 + (0.62 * self._border_progress)))
        border_gradient.setColorAt(1.0, blend(PALETTE.surface_alt, self._accent_color, 0.18 + (0.44 * self._border_progress)))
        border_pen = QPen()
        border_pen.setWidthF(1.25)
        border_pen.setBrush(QBrush(border_gradient))
        painter.setPen(border_pen)
        painter.drawPath(path)

        if not self.isEnabled():
            painter.fillPath(path, with_alpha(PALETTE.disabled_fill, 150))

        super().paintEvent(event)


__all__ = ["ModernLineEdit"]
