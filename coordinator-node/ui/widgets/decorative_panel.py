"""Reusable decorative panel with subtle animated cybersecurity motion."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Property, QRectF, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget

from .modern_button import PALETTE, blend, with_alpha


class DecorativePanel(QFrame):
    """Lightweight animated panel for authentication and dashboard surfaces."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._tick)

        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("decorativePanel")
        self.setStyleSheet("QFrame#decorativePanel { background: transparent; border: none; }")
        self._timer.start()

    def _tick(self) -> None:
        self.phase = (self._phase + 0.0075) % 1.0

    def getPhase(self) -> float:
        return self._phase

    def setPhase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = Property(float, getPhase, setPhase)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(PALETTE.background))
        base.setColorAt(0.45, blend(PALETTE.surface, PALETTE.surface_alt, 0.55))
        base.setColorAt(1.0, QColor(PALETTE.background))
        painter.fillRect(rect, base)

        self._paint_orb(painter, rect, 0.18, 0.24, 160, 0.0)
        self._paint_orb(painter, rect, 0.82, 0.35, 130, math.pi / 3)
        self._paint_orb(painter, rect, 0.42, 0.82, 100, math.pi / 1.4)
        self._paint_grid(painter, rect)
        self._paint_signal_arcs(painter, rect)
        self._paint_frame(painter, rect)

    def _paint_orb(
        self,
        painter: QPainter,
        rect: QRectF,
        x_ratio: float,
        y_ratio: float,
        radius: float,
        phase_shift: float,
    ) -> None:
        drift = math.sin((self._phase * math.tau) + phase_shift)
        center_x = rect.left() + (rect.width() * x_ratio) + (drift * 18)
        center_y = rect.top() + (rect.height() * y_ratio) + (math.cos((self._phase * math.tau) + phase_shift) * 14)
        gradient = QRadialGradient(center_x, center_y, radius)
        gradient.setColorAt(0.0, with_alpha(PALETTE.accent_bright, 56))
        gradient.setColorAt(0.42, with_alpha(PALETTE.accent_soft, 30))
        gradient.setColorAt(1.0, with_alpha(PALETTE.background, 0))
        painter.setPen(QPen(with_alpha(PALETTE.accent_alt, 24), 1.0))
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setClipRect(rect)
        grid_pen = QPen(with_alpha(PALETTE.accent_soft, 20), 1.0)
        painter.setPen(grid_pen)
        spacing = 34
        offset = int(self._phase * spacing)
        for x in range(-spacing, int(rect.width()) + spacing, spacing):
            painter.drawLine(int(rect.left()) + x + offset, int(rect.top()), int(rect.left()) + x - 22 + offset, int(rect.bottom()))
        for y in range(0, int(rect.height()) + spacing, spacing):
            painter.drawLine(int(rect.left()), int(rect.top()) + y, int(rect.right()), int(rect.top()) + y)
        painter.restore()

    def _paint_signal_arcs(self, painter: QPainter, rect: QRectF) -> None:
        center_x = rect.width() * 0.5
        center_y = rect.height() * 0.55
        sweep_base = 110 + (math.sin(self._phase * math.tau) * 18)
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(-12)
        for index, diameter in enumerate((140, 220, 300)):
            alpha = 46 - (index * 10)
            pen = QPen(with_alpha(PALETTE.accent_bright, alpha), 1.2)
            painter.setPen(pen)
            arc_rect = QRectF(-diameter / 2, -diameter / 2, diameter, diameter)
            start_angle = int((20 + (index * 12)) * 16)
            span_angle = int(sweep_base * 16)
            painter.drawArc(arc_rect, start_angle, span_angle)
        painter.restore()

    def _paint_frame(self, painter: QPainter, rect: QRectF) -> None:
        panel_rect = rect.adjusted(14, 14, -14, -14)
        path = QPainterPath()
        path.addRoundedRect(panel_rect, 22, 22)

        painter.setPen(QPen(with_alpha(PALETTE.accent_alt, 36), 1.0))
        painter.drawPath(path)

        inner_rect = panel_rect.adjusted(18, 18, -18, -18)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner_rect, 16, 16)
        painter.setPen(QPen(with_alpha(PALETTE.text, 12), 1.0))
        painter.drawPath(inner_path)


__all__ = ["DecorativePanel"]
