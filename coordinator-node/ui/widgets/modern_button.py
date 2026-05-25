"""Reusable button for the desktop security UI.

Drop-in replacement for ui/widgets/modern_button.py.
Keeps the old public API:
- ModernButton
- set_loading(bool, text=None)
- set_accent_color(color)
- set_button_style(...)
- PALETTE / blend / to_color / with_alpha
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.fonts import app_font, ui_font_family


@dataclass(frozen=True)
class CyberPalette:
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
    danger: str = "#cf334f"
    danger_alt: str = "#e14a61"
    danger_soft: str = "#ff7086"
    icon_surface: str = "#0f1727"
    icon_surface_alt: str = "#172033"
    icon_border: str = "#2a7252"


PALETTE = CyberPalette()


def to_color(value: QColor | str) -> QColor:
    return value if isinstance(value, QColor) else QColor(value)


def with_alpha(color: QColor | str, alpha: int) -> QColor:
    c = QColor(to_color(color))
    c.setAlpha(max(0, min(alpha, 255)))
    return c


def blend(color_a: QColor | str, color_b: QColor | str, ratio: float) -> QColor:
    ratio = max(0.0, min(ratio, 1.0))
    a = to_color(color_a)
    b = to_color(color_b)
    return QColor(
        int(a.red() + (b.red() - a.red()) * ratio),
        int(a.green() + (b.green() - a.green()) * ratio),
        int(a.blue() + (b.blue() - a.blue()) * ratio),
        int(a.alpha() + (b.alpha() - a.alpha()) * ratio),
    )


class ModernButton(QPushButton):
    """Clean rounded button with subtle hover/press/loading states."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None, *, variant: str = "primary") -> None:
        super().__init__(text, parent)

        self._variant = variant
        self._accent_color = QColor(PALETTE.accent)
        self._accent_color_alt = QColor(PALETTE.accent_alt)
        self._text_color = QColor("#ffffff")
        self._radius = 10
        self._custom_accent = False

        self._hover_progress = 0.0
        self._press_progress = 0.0

        self._loading = False
        self._cached_text = text
        self._spinner_angle = 0

        self._hover_animation = self._build_animation(b"hoverProgress", 170)
        self._press_animation = self._build_animation(b"pressProgress", 95)

        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(22)
        self._spinner_timer.timeout.connect(self._advance_spinner)

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFont(app_font(10, QFont.DemiBold))
        self.setCheckable(False)
        self.setFlat(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setIconSize(QSize(18, 18))
        self.set_variant(variant)
        self.set_button_style()

    def _build_animation(self, prop_name: bytes, duration: int) -> QPropertyAnimation:
        animation = QPropertyAnimation(self, prop_name, self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        return animation

    def _animate(self, animation: QPropertyAnimation, start: float, end: float) -> None:
        animation.stop()
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.start()

    def _advance_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 18) % 360
        self.update()

    def sizeHint(self):
        hint = super().sizeHint()
        if self._variant == "icon":
            icon_side = max(42, self.minimumHeight(), self.iconSize().width() + 24)
            hint.setHeight(icon_side)
            hint.setWidth(icon_side)
            return hint
        hint.setHeight(max(hint.height(), 46))
        hint.setWidth(max(hint.width(), 132))
        return hint

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and not self._loading:
            self._animate(self._hover_animation, self._hover_progress, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate(self._hover_animation, self._hover_progress, 0.0)
        self._animate(self._press_animation, self._press_progress, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled() and not self._loading:
            self._animate(self._press_animation, self._press_progress, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and not self._loading:
            target_hover = 1.0 if self.rect().contains(event.position().toPoint()) else 0.0
            self._animate(self._press_animation, self._press_progress, 0.0)
            self._animate(self._hover_animation, self._hover_progress, target_hover)
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if not self.isEnabled():
            self._animate(self._hover_animation, self._hover_progress, 0.0)
            self._animate(self._press_animation, self._press_progress, 0.0)
        super().changeEvent(event)

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
        self._loading = is_loading
        if text is not None:
            self._cached_text = text
        if is_loading:
            self.setCursor(Qt.BusyCursor)
            self._spinner_angle = 0
            self._spinner_timer.start()
            self._animate(self._press_animation, self._press_progress, 0.0)
        else:
            self._spinner_timer.stop()
            self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)
        self.update()

    def set_accent_color(self, color: QColor | str) -> None:
        self._custom_accent = True
        self._accent_color = to_color(color)
        self._accent_color_alt = blend(self._accent_color, "#ffffff", 0.14)
        self.update()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        if not self._custom_accent:
            if variant == "danger":
                self._accent_color = QColor(PALETTE.danger)
                self._accent_color_alt = QColor(PALETTE.danger_alt)
            elif variant == "icon":
                self._accent_color = QColor(PALETTE.icon_surface)
                self._accent_color_alt = QColor(PALETTE.icon_surface_alt)
            else:
                self._accent_color = QColor(PALETTE.accent)
                self._accent_color_alt = QColor(PALETTE.accent_alt)
        if variant == "icon":
            self._radius = 10
            self.setMinimumSize(42, 42)
            self.setMaximumWidth(42)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            self.setMinimumSize(0, 46)
            self.setMinimumHeight(46)
            self.setMaximumWidth(16777215)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update()

    def set_button_style(
        self,
        *,
        radius: Optional[int] = None,
        background_color: Optional[QColor | str] = None,
        background_alt: Optional[QColor | str] = None,
        text_color: Optional[QColor | str] = None,
    ) -> None:
        """Keep backward compatibility with old calls.

        background_color/background_alt are intentionally accepted but only lightly used
        because this component now owns the green premium button identity globally.
        """
        if radius is not None:
            self._radius = max(10, radius)
        if background_color is not None:
            self._custom_accent = True
            self._accent_color = blend(background_color, self._accent_color, 0.72)
        if background_alt is not None:
            self._custom_accent = True
            self._accent_color_alt = blend(background_alt, self._accent_color_alt, 0.72)
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
                margin: 0;
            }}
            QPushButton:disabled {{
                color: {PALETTE.disabled_text};
            }}
            """
        )
        self.update()

    def _button_rect(self) -> QRectF:
        press_inset = 0.9 * self._press_progress
        edge_inset = 1.5
        return QRectF(self.rect()).adjusted(
            edge_inset + press_inset,
            edge_inset + press_inset,
            -edge_inset - press_inset,
            -edge_inset - press_inset,
        )

    def _rounded_path(self, rect: QRectF) -> QPainterPath:
        radius = min(self._radius, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self._button_rect()
        path = self._rounded_path(rect)

        if not self.isEnabled():
            self._paint_disabled(painter, rect, path)
            self._paint_content(painter, rect, QColor(PALETTE.disabled_text))
            return

        self._paint_fill(painter, rect, path)
        self._paint_border(painter, rect, path)

        if self._loading:
            self._paint_spinner(painter, rect)

        self._paint_content(painter, rect, self._text_color)

    def _paint_fill(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        hover = self._hover_progress
        press = self._press_progress
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if self._variant == "icon":
            gradient.setColorAt(0.00, blend(self._accent_color, "#ffffff", 0.01 + hover * 0.015))
            gradient.setColorAt(1.00, blend(self._accent_color_alt, "#000000", 0.08 + press * 0.06))
        else:
            gradient.setColorAt(0.00, blend(self._accent_color, "#ffffff", 0.05 + hover * 0.025))
            gradient.setColorAt(1.00, blend(self._accent_color_alt, "#10141d", 0.10 + press * 0.08))
        painter.fillPath(path, gradient)

    def _paint_border(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        border = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if self._variant == "icon":
            border.setColorAt(0.0, with_alpha(blend(PALETTE.icon_border, "#7fffc5", 0.10), 112 + int(18 * self._hover_progress)))
            border.setColorAt(1.0, with_alpha(blend(PALETTE.icon_border, "#0d111a", 0.16), 124))
        else:
            border.setColorAt(0.0, with_alpha(blend(self._accent_color_alt, "#ffffff", 0.08), 126 + int(14 * self._hover_progress)))
            border.setColorAt(1.0, with_alpha(blend(self._accent_color, "#10141d", 0.24), 138))
        pen = QPen(border, 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        inner = self._rounded_path(rect.adjusted(1.25, 1.25, -1.25, -1.25))
        inner_alpha = 22 if self._variant == "icon" else 28
        painter.setPen(QPen(with_alpha("#000000", inner_alpha), 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(inner)

    def _paint_disabled(self, painter: QPainter, rect: QRectF, path: QPainterPath) -> None:
        painter.fillPath(path, QColor(PALETTE.disabled_fill))
        painter.setPen(QPen(with_alpha(PALETTE.border, 150), 1.0))
        painter.drawPath(path)

    def _paint_content(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        text = self._cached_text if self._loading and self._cached_text else self.text()
        icon = self.icon()
        has_icon = not icon.isNull()
        has_text = bool(text)

        inset = 10 if self._variant == "icon" else 14
        content_rect = QRectF(rect).adjusted(inset, 0, -inset, 0)
        if self._loading:
            content_rect.adjust(20, 0, 0, 0)

        if has_icon:
            pixmap = icon.pixmap(self.iconSize(), QIcon.Mode.Normal, QIcon.State.Off)
            self._paint_icon_and_text(painter, content_rect, pixmap, text if has_text else "", color)
            return

        self._paint_text_only(painter, content_rect, text, color)

    def _paint_icon_and_text(self, painter: QPainter, rect: QRectF, pixmap: QPixmap, text: str, color: QColor) -> None:
        if pixmap.isNull():
            self._paint_text_only(painter, rect, text, color)
            return
        if not text:
            icon_x = rect.center().x() - pixmap.width() / 2.0
            icon_y = rect.center().y() - pixmap.height() / 2.0
            painter.drawPixmap(round(icon_x), round(icon_y), pixmap)
            return

        spacing = 10
        total_width = pixmap.width() + spacing + max(0, painter.fontMetrics().horizontalAdvance(text))
        start_x = rect.center().x() - total_width / 2
        icon_y = rect.center().y() - pixmap.height() / 2
        painter.drawPixmap(round(start_x), round(icon_y), pixmap)

        text_rect = QRectF(start_x + pixmap.width() + spacing, rect.top(), rect.right() - start_x, rect.height())
        self._paint_text_only(painter, text_rect, text, color, alignment=Qt.AlignVCenter | Qt.AlignLeft)

    def _paint_text_only(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        color: QColor,
        *,
        alignment: Qt.AlignmentFlag | Qt.Alignment = Qt.AlignCenter,
    ) -> None:
        font = painter.font()
        font.setBold(True)
        if self._variant == "icon":
            font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, alignment, text)

    def _paint_spinner(self, painter: QPainter, rect: QRectF) -> None:
        spinner_size = 14
        cx = rect.center().x() - 52
        cy = rect.center().y()
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._spinner_angle)
        for index in range(12):
            color = with_alpha("#ffffff", int(35 + index * 16))
            painter.setPen(QPen(color, 2.1, Qt.SolidLine, Qt.RoundCap))
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
