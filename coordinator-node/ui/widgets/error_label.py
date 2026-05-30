"""Reusable animated validation label."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ui.fonts import ui_font, ui_font_family

class ErrorLabel(QLabel):
    """Floating toast-style validation label with smooth fade transitions."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("toastErrorLabel")
        self._effect = QGraphicsOpacityEffect(self)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._hide_timer = QTimer(self)
        self._anchor_parent: Optional[QWidget] = parent
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_error)

        self._animation.setDuration(240)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self.setVisible(False)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(ui_font(10, 500))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMaximumWidth(360)
        self.setMinimumHeight(44)
        self.setStyleSheet(
            f"""
            QLabel#toastErrorLabel {{
                color: #ffb2bf;
                background-color: rgba(39, 15, 24, 236);
                border: 1px solid rgba(255, 91, 121, 168);
                border-radius: 12px;
                padding: 10px 14px;
                font-family: "{ui_font_family()}";
                font-size: 12px;
                font-weight: 500;
            }}
            """
        )

    def show_error(self, message: str, timeout_ms: int = 3200) -> None:
        """Show an error message and optionally auto-hide it."""
        if not str(message).strip():
            self.hide_error()
            return
        self._hide_timer.stop()
        self._animation.stop()
        self.setText(message)
        self.move_to_top_center(self._anchor_parent or self.parentWidget())
        start_opacity = self._effect.opacity() if self.isVisible() else 0.16
        self._effect.setOpacity(max(0.16, start_opacity))
        self.show()
        self.raise_()
        self.update()
        self._fade_to(1.0)
        if timeout_ms > 0:
            self._hide_timer.start(timeout_ms)

    def hide_error(self) -> None:
        """Fade the error out and then hide the label."""
        if not self.isVisible() and self._effect.opacity() <= 0.01:
            return
        self._hide_timer.stop()
        self._fade_to(0.0, hide_after=True)

    def _fade_to(self, value: float, hide_after: bool = False) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(value)
        try:
            self._animation.finished.disconnect(self._hide_if_transparent)
        except (RuntimeError, TypeError):
            pass
        if hide_after:
            self._animation.finished.connect(self._hide_if_transparent)
        self._animation.start()

    def _hide_if_transparent(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.setVisible(False)
        try:
            self._animation.finished.disconnect(self._hide_if_transparent)
        except (RuntimeError, TypeError):
            pass

    def move_to_top_center(self, parent_widget: Optional[QWidget]) -> None:
        """Position the toast near the top center of its parent without affecting layout."""
        if parent_widget is None:
            return
        self._anchor_parent = parent_widget
        if self.parentWidget() is not parent_widget:
            self.setParent(parent_widget)
        bounds = parent_widget.contentsRect()
        available_width = max(220, bounds.width() - 48)
        max_width = min(available_width, 400)
        self.setFixedWidth(max_width)
        self.adjustSize()
        x = bounds.x() + max(24, (bounds.width() - self.width()) // 2)
        y = bounds.y() + 18
        self.move(x, y)
        self.raise_()


__all__ = ["ErrorLabel"]
