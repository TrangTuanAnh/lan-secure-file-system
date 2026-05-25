"""Reusable horizontal activity ticker for dashboard activity feeds."""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget

from ui.fonts import app_font


class ActivityTicker(QFrame):
    """Loop activity messages from right to left without blocking the UI."""

    BACKGROUND_COLOR = QColor(244, 251, 247, 245)
    BORDER_COLOR = QColor(205, 228, 214, 230)
    TEXT_COLOR = QColor(21, 58, 43)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityTicker")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(52)

        self._messages: list[str] = []
        self._display_text = "NO RECENT ACTIVITY YET"
        self._offset = 0.0
        self._text_width = 0
        self._gap = 28

        self._timer = QTimer(self)
        self._timer.setInterval(24)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

        self.setFont(app_font(11, 700))
        self._rebuild_display_text()

    def set_messages(self, messages: Iterable[str]) -> None:
        cleaned = [str(message).strip().upper() for message in messages if str(message).strip()]
        self._messages = cleaned
        self._rebuild_display_text()
        self.update()

    def append_message(self, message: str) -> None:
        normalized = str(message).strip().upper()
        if not normalized:
            return
        self._messages.append(normalized)
        self._messages = self._messages[-10:]
        self._rebuild_display_text()
        self.update()

    def _rebuild_display_text(self) -> None:
        if not self._messages:
            self._display_text = "NO RECENT ACTIVITY YET"
        else:
            self._display_text = " - ".join(self._messages)

        metrics = QFontMetrics(self.font())
        self._text_width = metrics.horizontalAdvance(self._display_text)
        self._offset = float(self.width())

    def _advance(self) -> None:
        if self.width() <= 0:
            return
        self._offset -= 1.6
        if self._offset <= -(self._text_width + self._gap):
            self._offset = float(self.width())
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._offset == 0.0:
            self._offset = float(self.width())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        frame_rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(self.BACKGROUND_COLOR)
        painter.drawRoundedRect(frame_rect, 10, 10)

        painter.setFont(self.font())
        painter.setPen(self.TEXT_COLOR)
        painter.setClipRect(self.rect().adjusted(16, 0, -16, 0))
        text_y = int((self.height() + painter.fontMetrics().ascent() - painter.fontMetrics().descent()) / 2)
        cycle_width = max(1, self._text_width + self._gap)
        start_x = int(self._offset)

        while start_x > 16:
            start_x -= cycle_width

        draw_x = start_x
        max_x = self.width() + cycle_width
        while draw_x < max_x:
            painter.drawText(draw_x, text_y, self._display_text)
            draw_x += cycle_width


__all__ = ["ActivityTicker"]
