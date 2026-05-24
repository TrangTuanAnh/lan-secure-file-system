"""Dashboard KPI card matching the application's dark enterprise aesthetic."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, to_color, with_alpha


class DashboardStatCard(QFrame):
    """Stat summary card with icon, title, value, and supporting text."""

    def __init__(
        self,
        title: str = "",
        value: str = "",
        subtitle: str = "",
        icon_text: str = "",
        accent_color: QColor | str = PALETTE.accent_alt,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._accent = to_color(accent_color)

        self.setObjectName("dashboardStatCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(146)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        self.icon_label = QLabel(icon_text)
        self.icon_label.setObjectName("statCardIcon")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setMinimumSize(42, 42)
        self.icon_label.setMaximumSize(42, 42)
        self.icon_label.setFont(ui_font(11, 700))
        top_row.addWidget(self.icon_label, 0, Qt.AlignLeft | Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setFont(ui_font(10, 600))
        text_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(ui_font(9))
        self.subtitle_label.setWordWrap(True)
        text_col.addWidget(self.subtitle_label)
        top_row.addLayout(text_col, 1)
        root.addLayout(top_row)

        self.value_label = QLabel(value)
        self.value_label.setFont(app_font(22, 700))
        root.addWidget(self.value_label)

        self._apply_styles()

    def _apply_styles(self) -> None:
        accent_soft = with_alpha(self._accent, 30).name(QColor.HexArgb)
        accent_medium = with_alpha(self._accent, 110).name(QColor.HexArgb)
        accent_border = with_alpha(self._accent, 70).name(QColor.HexArgb)
        self.setStyleSheet(
            f"""
            QFrame#dashboardStatCard {{
                background-color: rgba(26, 26, 46, 228);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 22px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#statCardIcon {{
                background: transparent;
            }}
            """
        )
        self.icon_label.setStyleSheet(
            f"""
            QLabel {{
                color: {self._accent.name()};
                background-color: {accent_soft};
                border: 1px solid {accent_border};
                border-radius: 14px;
            }}
            """
        )
        self.title_label.setStyleSheet("color: #f4fff9;")
        self.subtitle_label.setStyleSheet("color: #8aa39a;")
        self.value_label.setStyleSheet(
            f"""
            color: #f4fff9;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            padding-top: 12px;
            """
        )

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)

    def set_icon_text(self, text: str) -> None:
        self.icon_label.setText(text)

    def set_accent_color(self, color: QColor | str) -> None:
        self._accent = to_color(color)
        self._apply_styles()


__all__ = ["DashboardStatCard"]
