"""Reusable dashboard sidebar navigation widget."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui.fonts import app_font, brand_font, brand_font_family, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, with_alpha


class SidebarNav(QFrame):
    """Sidebar with brand, user summary, and navigation items."""

    navigation_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.idClicked.connect(self._emit_navigation_requested)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._button_ids: list[str] = []

        self.setObjectName("sidebarNav")
        self.setMinimumWidth(280)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 24, 22, 24)
        layout.setSpacing(18)

        self.brand_label = QLabel("LAN Secure File System")
        self.brand_label.setFont(brand_font(18))
        self.brand_label.setWordWrap(True)
        layout.addWidget(self.brand_label)

        self.user_card = QFrame()
        self.user_card.setObjectName("sidebarUserCard")
        user_layout = QVBoxLayout(self.user_card)
        user_layout.setContentsMargins(16, 16, 16, 16)
        user_layout.setSpacing(6)

        self.user_name_label = QLabel("Security Operator")
        self.user_name_label.setFont(app_font(11, 600))
        user_layout.addWidget(self.user_name_label)

        self.user_email_label = QLabel("operator@coordinator.local")
        self.user_email_label.setFont(ui_font(9))
        user_layout.addWidget(self.user_email_label)

        self.user_role_label = QLabel("Operations Control")
        self.user_role_label.setFont(ui_font(9))
        user_layout.addWidget(self.user_role_label)
        layout.addWidget(self.user_card)

        self.nav_container = QFrame()
        self.nav_container.setObjectName("sidebarNavSection")
        nav_layout = QVBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(8)
        self._nav_layout = nav_layout
        layout.addWidget(self.nav_container)

        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#sidebarNav {{
                background-color: rgba(15, 15, 30, 244);
                border-right: 1px solid rgba(0, 200, 83, 32);
            }}
            QFrame#sidebarUserCard,
            QFrame#sidebarNavSection {{
                background-color: rgba(26, 26, 46, 214);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 20px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QPushButton {{
                font-family: "{ui_font_family()}";
            }}
            QPushButton#sidebarNavButton {{
                text-align: left;
                padding: 12px 14px;
                color: #d8ebe2;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 16px;
            }}
            QPushButton#sidebarNavButton:hover {{
                background-color: rgba(0, 200, 83, 18);
                border-color: rgba(0, 200, 83, 48);
            }}
            QPushButton#sidebarNavButton:checked {{
                color: #f4fff9;
                background-color: rgba(0, 200, 83, 24);
                border-color: rgba(0, 200, 83, 70);
            }}
            """
        )
        self.brand_label.setStyleSheet(
            f"""
            color: {PALETTE.text};
            font-family: "{brand_font_family()}";
            letter-spacing: 0.3px;
            """
        )
        self.user_name_label.setStyleSheet("color: #f4fff9;")
        self.user_email_label.setStyleSheet("color: #8aa39a;")
        self.user_role_label.setStyleSheet(
            f"color: {with_alpha(PALETTE.accent_soft, 230).name()};"
        )

    def add_nav_item(self, item_id: str, label: str, checked: bool = False) -> None:
        """Add a reusable sidebar navigation button."""
        button = QPushButton(label)
        button.setObjectName("sidebarNavButton")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setFont(app_font(10, 600))
        self._button_ids.append(item_id)
        self._button_group.addButton(button, len(self._button_ids) - 1)
        self._nav_buttons[item_id] = button
        self._nav_layout.addWidget(button)
        if checked:
            self.set_current_item(item_id)

    def set_current_item(self, item_id: str) -> None:
        button = self._nav_buttons.get(item_id)
        if button is not None:
            button.setChecked(True)

    def set_user_info(self, name: str, email: str, role: str) -> None:
        self.user_name_label.setText(name)
        self.user_email_label.setText(email)
        self.user_role_label.setText(role)

    def _emit_navigation_requested(self, button_id: int) -> None:
        if 0 <= button_id < len(self._button_ids):
            self.navigation_requested.emit(self._button_ids[button_id])


__all__ = ["SidebarNav"]
