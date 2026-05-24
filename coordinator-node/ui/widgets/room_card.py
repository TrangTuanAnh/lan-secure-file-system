"""Reusable room summary card for dashboards and room listings."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, ModernButton, to_color
from ui.widgets.status_badge import StatusBadge


class RoomCard(QFrame):
    """Room overview card with metadata and open action."""

    open_requested = Signal(str)

    def __init__(
        self,
        room_id: str = "",
        room_name: str = "",
        role: str = "Member",
        file_count: int = 0,
        member_count: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._room_id = room_id
        self.setObjectName("roomCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(176)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        self.room_name_label = QLabel(room_name)
        self.room_name_label.setFont(app_font(15, 600))
        title_col.addWidget(self.room_name_label)

        self.room_id_label = QLabel(room_id)
        self.room_id_label.setFont(ui_font(9))
        title_col.addWidget(self.room_id_label)
        header.addLayout(title_col, 1)

        self.role_badge = StatusBadge(role.upper(), variant=role.lower())
        header.addWidget(self.role_badge, 0, Qt.AlignTop)
        root.addLayout(header)

        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(12)
        self.file_count_label = self._build_metric("Files", str(file_count))
        self.member_count_label = self._build_metric("Members", str(member_count))
        stats.addWidget(self.file_count_label, 1)
        stats.addWidget(self.member_count_label, 1)
        root.addLayout(stats)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)

        self.summary_label = QLabel("Secure collaborative room with encrypted document access.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setFont(ui_font(9))
        footer.addWidget(self.summary_label, 1)

        self.open_button = ModernButton("Open Room")
        self.open_button.setMinimumWidth(130)
        self.open_button.clicked.connect(self._emit_open_requested)
        footer.addWidget(self.open_button, 0, Qt.AlignBottom)
        root.addLayout(footer)

        self._apply_styles()

    def _build_metric(self, title: str, value: str) -> QFrame:
        container = QFrame()
        container.setObjectName("roomMetric")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setFont(app_font(16, 700))
        layout.addWidget(value_label)

        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        title_label.setFont(ui_font(9))
        layout.addWidget(title_label)
        return container

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#roomCard {{
                background-color: rgba(26, 26, 46, 226);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 22px;
            }}
            QFrame#roomMetric {{
                background-color: rgba(15, 15, 30, 168);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#metricValue {{
                color: #f4fff9;
            }}
            QLabel#metricTitle {{
                color: #8aa39a;
            }}
            """
        )
        self.room_name_label.setStyleSheet("color: #f4fff9;")
        self.room_id_label.setStyleSheet("color: #7f948d;")
        self.summary_label.setStyleSheet("color: #8aa39a;")

    def _emit_open_requested(self) -> None:
        self.open_requested.emit(self._room_id)

    def set_room_id(self, room_id: str) -> None:
        self._room_id = room_id
        self.room_id_label.setText(room_id)

    def set_room_name(self, room_name: str) -> None:
        self.room_name_label.setText(room_name)

    def set_role(self, role: str, accent_color: Optional[QColor | str] = None) -> None:
        self.role_badge.setText(role.upper())
        self.role_badge.set_variant(role.lower())
        if accent_color is not None:
            self.role_badge.set_accent_color(accent_color)

    def set_counts(self, file_count: int, member_count: int) -> None:
        for metric, value in (
            (self.file_count_label, file_count),
            (self.member_count_label, member_count),
        ):
            value_label = metric.findChild(QLabel, "metricValue")
            if value_label is not None:
                value_label.setText(str(value))

    def set_summary(self, summary: str) -> None:
        self.summary_label.setText(summary)


__all__ = ["RoomCard"]
