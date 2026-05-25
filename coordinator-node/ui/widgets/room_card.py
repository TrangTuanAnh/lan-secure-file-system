"""Reusable room card for secure room listings and dashboard sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.room_data import normalize_room_payload
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.status_badge import StatusBadge


ROLE_VARIANTS = {
    "owner": "owner",
    "admin": "active",
    "member": "member",
    "viewer": "viewer",
}
_JOIN_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "icon" / "join.png"


class RoomCard(QFrame):
    """Display room metadata and emit an open signal without page logic."""

    open_requested = Signal(str)

    def __init__(
        self,
        room_id: str = "",
        room_name: str = "",
        role: str = "Member",
        file_count: int = 0,
        member_count: int = 0,
        last_activity: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._room_data: dict[str, Any] = {}
        self.setObjectName("roomCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(172)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        title_column = QVBoxLayout()
        title_column.setContentsMargins(0, 0, 0, 0)
        title_column.setSpacing(5)

        self.room_name_label = QLabel("")
        self.room_name_label.setObjectName("roomNameLabel")
        self.room_name_label.setFont(app_font(15, 600))
        title_column.addWidget(self.room_name_label)

        self.room_id_label = QLabel("")
        self.room_id_label.setObjectName("roomIdLabel")
        self.room_id_label.setFont(ui_font(9))
        self.room_id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_column.addWidget(self.room_id_label)
        header.addLayout(title_column, 1)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        self.role_badge = StatusBadge("ROOM ROLE", variant="member")
        actions_row.addWidget(self.role_badge, 0, Qt.AlignVCenter)

        self.open_button = ModernButton("", variant="icon")
        self.open_button.clicked.connect(self._emit_open_requested)
        self.open_button.setToolTip("Open Room")
        self.open_button.setAccessibleName("Open Room")
        if _JOIN_ICON_PATH.exists():
            self.open_button.setIcon(QIcon(str(_JOIN_ICON_PATH)))
            self.open_button.setIconSize(QSize(18, 18))
            self.open_button.setText("")
        else:
            self.open_button.set_variant("primary")
            self.open_button.setText("Open")
        actions_row.addWidget(self.open_button, 0, Qt.AlignVCenter)

        header.addLayout(actions_row, 0)
        root.addLayout(header)

        metric_row = QHBoxLayout()
        metric_row.setContentsMargins(0, 0, 0, 0)
        metric_row.setSpacing(12)
        self.member_metric = self._build_metric("Members", "0")
        self.file_metric = self._build_metric("Files", "0")
        metric_row.addWidget(self.member_metric, 1)
        metric_row.addWidget(self.file_metric, 1)
        root.addLayout(metric_row)

        self._apply_styles()
        self.set_room_data(
            {
                "room_id": room_id,
                "room_name": room_name,
                "role": role,
                "file_count": file_count,
                "member_count": member_count,
                "last_activity": last_activity,
            }
        )

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
                background-color: rgba(26, 26, 46, 224);
                border: 1px solid rgba(0, 200, 83, 44);
                border-radius: 22px;
            }}
            QFrame#roomMetric {{
                background-color: rgba(15, 15, 30, 176);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#roomNameLabel,
            QLabel#metricValue {{
                color: #f4fff9;
            }}
            QLabel#roomIdLabel {{
                color: #7f948d;
            }}
            QLabel#metricTitle {{
                color: #8aa39a;
            }}
            """
        )

    def _set_metric_value(self, metric: QFrame, value: int) -> None:
        value_label = metric.findChild(QLabel, "metricValue")
        if value_label is not None:
            value_label.setText(str(max(0, int(value))))

    def _role_variant(self, role: str) -> str:
        return ROLE_VARIANTS.get(role.strip().lower(), "member")

    def _emit_open_requested(self) -> None:
        self.open_requested.emit(self.room_id)

    @property
    def room_id(self) -> str:
        return str(self._room_data.get("room_id", ""))

    def set_room_data(self, room_data: dict[str, Any]) -> None:
        """Update the card from a normalized room payload."""
        normalized = normalize_room_payload(room_data)
        self._room_data = normalized

        self.room_name_label.setText(str(normalized["room_name"]))
        self.room_id_label.setText(str(normalized["room_id"]) or "Room ID unavailable")
        self._set_metric_value(self.member_metric, int(normalized["member_count"]))
        self._set_metric_value(self.file_metric, int(normalized["file_count"]))
        self.set_role(str(normalized["role"]))

    def set_room_id(self, room_id: str) -> None:
        data = dict(self._room_data)
        data["room_id"] = room_id
        self.set_room_data(data)

    def set_room_name(self, room_name: str) -> None:
        data = dict(self._room_data)
        data["room_name"] = room_name
        self.set_room_data(data)

    def set_role(self, role: str) -> None:
        normalized_role = role.strip().upper()
        has_room_role = bool(normalized_role)
        self.role_badge.setVisible(has_room_role)
        if has_room_role:
            self.role_badge.setText(normalized_role)
            self.role_badge.set_variant(self._role_variant(role))
        data = dict(self._room_data)
        data["role"] = role
        self._room_data = data

    def set_counts(self, file_count: int, member_count: int) -> None:
        data = dict(self._room_data)
        data["file_count"] = file_count
        data["member_count"] = member_count
        self.set_room_data(data)

    def set_summary(self, summary: str) -> None:
        data = dict(self._room_data)
        data["summary"] = summary
        self.set_room_data(data)

    def set_last_activity(self, last_activity: str) -> None:
        data = dict(self._room_data)
        data["last_activity"] = last_activity
        self.set_room_data(data)


__all__ = ["RoomCard"]
