"""Reusable recent-activity row for dashboard timelines."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, to_color, with_alpha
from ui.widgets.status_badge import StatusBadge


class ActivityItem(QFrame):
    """Single activity row with type badge, message, and timestamp."""

    def __init__(
        self,
        activity_type: str = "Activity",
        message: str = "",
        timestamp: str = "",
        accent_color: QColor | str = PALETTE.accent_alt,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._accent = to_color(accent_color)
        self.setObjectName("activityItem")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        self.type_badge = StatusBadge(activity_type.upper(), variant="active")
        self.type_badge.set_accent_color(self._accent)
        layout.addWidget(self.type_badge, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setFont(ui_font(10, 500))
        text_col.addWidget(self.message_label)

        self.timestamp_label = QLabel(timestamp)
        self.timestamp_label.setFont(ui_font(9))
        text_col.addWidget(self.timestamp_label)
        layout.addLayout(text_col, 1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#activityItem {{
                background-color: rgba(26, 26, 46, 205);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            """
        )
        self.message_label.setStyleSheet("color: #edf8f2;")
        self.timestamp_label.setStyleSheet(
            f"color: {with_alpha(PALETTE.text_muted, 225).name(QColor.HexArgb)};"
        )

    def set_activity_type(self, activity_type: str, accent_color: Optional[QColor | str] = None) -> None:
        self.type_badge.setText(activity_type.upper())
        if accent_color is not None:
            self.type_badge.set_accent_color(accent_color)

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def set_timestamp(self, timestamp: str) -> None:
        self.timestamp_label.setText(timestamp)


__all__ = ["ActivityItem"]
