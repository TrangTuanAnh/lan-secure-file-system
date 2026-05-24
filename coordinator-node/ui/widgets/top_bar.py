"""Reusable top bar for dashboard and app content screens."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, with_alpha
from ui.widgets.modern_lineedit import ModernLineEdit
from ui.widgets.status_badge import StatusBadge


class TopBar(QFrame):
    """Top bar with title, search, server status, and user display."""

    search_changed = Signal(str)

    def __init__(
        self,
        page_title: str = "",
        subtitle: str = "",
        search_placeholder: str = "Search rooms, files, or activity",
        user_display: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        self.title_label = QLabel(page_title)
        self.title_label.setFont(app_font(20, 700))
        title_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(ui_font(9))
        self.subtitle_label.setWordWrap(True)
        title_col.addWidget(self.subtitle_label)
        layout.addLayout(title_col, 1)

        self.search_input = ModernLineEdit(search_placeholder)
        self.search_input.setMinimumWidth(250)
        self.search_input.textChanged.connect(self.search_changed)
        layout.addWidget(self.search_input, 1)

        right_col = QHBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        self.server_badge = StatusBadge("ONLINE", "online")
        right_col.addWidget(self.server_badge)

        self.user_container = QFrame()
        self.user_container.setObjectName("topBarUserCard")
        user_layout = QHBoxLayout(self.user_container)
        user_layout.setContentsMargins(12, 10, 12, 10)
        user_layout.setSpacing(10)

        self.user_initials = QLabel("--")
        self.user_initials.setAlignment(Qt.AlignCenter)
        self.user_initials.setMinimumSize(34, 34)
        self.user_initials.setMaximumSize(34, 34)
        self.user_initials.setFont(ui_font(10, 700))
        user_layout.addWidget(self.user_initials)

        self.user_display_label = QLabel(user_display)
        self.user_display_label.setFont(ui_font(10, 600))
        user_layout.addWidget(self.user_display_label)
        right_col.addWidget(self.user_container)
        layout.addLayout(right_col)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#topBar {{
                background-color: rgba(26, 26, 46, 216);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 22px;
            }}
            QFrame#topBarUserCard {{
                background-color: rgba(15, 15, 30, 176);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            """
        )
        self.title_label.setStyleSheet("color: #f4fff9;")
        self.subtitle_label.setStyleSheet("color: #8aa39a;")
        self.user_initials.setStyleSheet(
            f"""
            color: {PALETTE.accent_bright};
            background-color: {with_alpha(PALETTE.accent_alt, 28).name()};
            border: 1px solid {with_alpha(PALETTE.accent_alt, 85).name()};
            border-radius: 17px;
            """
        )
        self.user_display_label.setStyleSheet("color: #edf8f2;")

    def set_page_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)

    def set_search_placeholder(self, placeholder: str) -> None:
        self.search_input.setPlaceholderText(placeholder)

    def set_server_status(self, label: str, variant: str = "online") -> None:
        self.server_badge.setText(label.upper())
        self.server_badge.set_variant(variant)

    def set_user_display(self, display_name: str) -> None:
        self.user_display_label.setText(display_name)
        initials = "".join(part[0] for part in display_name.split()[:2]).upper() if display_name else "--"
        self.user_initials.setText(initials or "--")


__all__ = ["TopBar"]
