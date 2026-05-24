"""Reusable premium line edit for the desktop security UI.

Drop-in replacement for ui/widgets/modern_lineedit.py.
Focus/hover effects are drawn inside the widget bounds so they do not look clipped.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QSizePolicy, QWidget

from ui.fonts import app_font, ui_font_family

from .modern_button import PALETTE, blend, to_color, with_alpha


class ModernLineEdit(QLineEdit):
    """Clean rounded input with premium in-bounds focus ring."""

    def __init__(self, placeholder_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._border_progress = 0.0
        self._focus_glow = 0.0
        self._hover_progress = 0.0
        self._radius = 15
        self._accent_color = QColor(PALETTE.accent_alt)
        self._background_color = QColor("#1b2634")

        self._hover_animation = self._build_animation(b"hoverProgress", 150)
        self._border_animation = self._build_animation(b"borderProgress", 170)
        self._glow_animation = self._build_animation(b"focusGlow", 190)

        self.setPlaceholderText(placeholder_text)
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFont(app_font(10))
        self.setFrame(False)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setAttribute(Qt.WA_Hover, True)
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
                selection-background-color: {with_alpha(PALETTE.accent_alt, 135).name(QColor.HexArgb)};
                selection-color: #ffffff;
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

    def _input_rect(self) -> QRectF:
        # Inset leaves enough room for focus ring inside widget boundaries.
        return QRectF(self.rect()).adjusted(3.0, 3.0, -3.0, -3.0)

    def _rounded_path(self, rect: QRectF) -> QPainterPath:
        radius = min(self._radius, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self._input_rect()
        path = self._rounded_path(rect)

        self._paint_fill(painter, rect, path)
        self._paint_focus_ring(painter, rect, path)
        self._paint_border(painter, rect, path)

        if not self.isEnabled():
            painter.fillPath(path, with_alpha(PALETTE.disabled_fill, 160))

        super().paintEvent(event)

    def _paint_fill(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        hover = self._hover_progress
        focus = self._focus_glow
        mix = 0.05 + 0.06 * hover + 0.08 * focus
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, blend(self._background_color, self._accent_color, mix))
        gradient.setColorAt(1.0, blend("#151d2b", self._accent_color, mix * 0.52))
        painter.fillPath(path, gradient)

        # Gentle top sheen, clipped inside the rounded rect.
        painter.save()
        painter.setClipPath(path)
        sheen_rect = QRectF(rect).adjusted(2, 2, -2, -rect.height() * 0.54)
        sheen = QLinearGradient(sheen_rect.topLeft(), sheen_rect.bottomLeft())
        sheen.setColorAt(0.0, with_alpha("#ffffff", 18 + int(18 * focus)))
        sheen.setColorAt(1.0, with_alpha("#ffffff", 0))
        painter.fillRect(sheen_rect, sheen)
        painter.restore()

    def _paint_focus_ring(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        if self._focus_glow <= 0.01:
            return

        # Draw glow inside the widget to avoid the chopped/cropped look.
        for inset, width, alpha in (
            (0.0, 3.0, int(95 * self._focus_glow)),
            (3.0, 1.5, int(115 * self._focus_glow)),
        ):
            ring_rect = rect.adjusted(inset, inset, -inset, -inset)
            ring_path = self._rounded_path(ring_rect)
            painter.setPen(QPen(with_alpha(self._accent_color, alpha), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(ring_path)

    def _paint_border(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        focus = self._border_progress
        hover = self._hover_progress
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, blend(PALETTE.border, self._accent_color, 0.24 + 0.52 * focus + 0.10 * hover))
        gradient.setColorAt(0.55, blend("#143f38", self._accent_color, 0.18 + 0.45 * focus + 0.08 * hover))
        gradient.setColorAt(1.0, blend(PALETTE.border, self._accent_color, 0.20 + 0.44 * focus + 0.08 * hover))
        painter.setPen(QPen(gradient, 1.25, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)


__all__ = ["ModernLineEdit"]
