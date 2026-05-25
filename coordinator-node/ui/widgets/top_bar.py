"""Reusable top bar for dashboard and app content screens."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.utils.avatar_resolver import render_svg_avatar, resolve_avatar_path
from ui.widgets.modern_button import PALETTE, with_alpha
from ui.widgets.modern_lineedit import ModernLineEdit
from ui.widgets.status_badge import StatusBadge


class TopBar(QFrame):
    """Top bar with title, search, server status, and user display."""

    search_changed = Signal(str)
    refresh_requested = Signal()
    account_requested = Signal()
    logout_requested = Signal()

    def __init__(
        self,
        page_title: str = "",
        subtitle: str = "",
        search_placeholder: str = "Search rooms, files, or activity",
        user_display: str = "",
        show_refresh_button: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._avatar_username = user_display
        self._avatar_user_id = ""
        self._avatar_global_role = "USER"
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

        self.refresh_button = QPushButton("↻")
        self.refresh_button.setObjectName("topBarRefreshButton")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.setToolTip("Refresh")
        self.refresh_button.setMinimumSize(42, 42)
        self.refresh_button.setMaximumSize(42, 42)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self._apply_refresh_icon()
        self.refresh_button.setVisible(show_refresh_button)
        layout.addWidget(self.refresh_button, 0, Qt.AlignVCenter)

        right_col = QHBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        self.server_badge = StatusBadge("ONLINE", "online")
        right_col.addWidget(self.server_badge)

        self.user_container = QFrame()
        self.user_container.setObjectName("topBarUserCard")
        self.user_container.setCursor(Qt.PointingHandCursor)
        user_layout = QHBoxLayout(self.user_container)
        user_layout.setContentsMargins(12, 10, 12, 10)
        user_layout.setSpacing(10)

        self.user_initials = QLabel("--")
        self.user_initials.setAlignment(Qt.AlignCenter)
        self.user_initials.setMinimumSize(34, 34)
        self.user_initials.setMaximumSize(34, 34)
        self.user_initials.setFont(ui_font(10, 700))
        user_layout.addWidget(self.user_initials)

        identity_layout = QVBoxLayout()
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(2)

        self.user_display_label = QLabel(user_display)
        self.user_display_label.setFont(ui_font(10, 600))
        identity_layout.addWidget(self.user_display_label)

        self.user_role_label = QLabel("Secure Operator")
        self.user_role_label.setObjectName("topBarUserRole")
        self.user_role_label.setFont(ui_font(8, 600))
        identity_layout.addWidget(self.user_role_label)
        user_layout.addLayout(identity_layout)
        right_col.addWidget(self.user_container)
        layout.addLayout(right_col)

        self._menu = self._build_user_menu()
        self.user_container.mousePressEvent = self._show_user_menu  # type: ignore[assignment]
        self.user_initials.mousePressEvent = self._show_user_menu  # type: ignore[assignment]
        self.user_display_label.mousePressEvent = self._show_user_menu  # type: ignore[assignment]
        self.user_role_label.mousePressEvent = self._show_user_menu  # type: ignore[assignment]

        self._apply_styles()
        self._update_avatar()

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
            QFrame#topBarUserCard:hover {{
                border-color: rgba(0, 200, 83, 70);
                background-color: rgba(18, 18, 36, 196);
            }}
            QPushButton#topBarRefreshButton {{
                background-color: rgba(15, 15, 30, 176);
                color: {PALETTE.text};
                border: 1px solid rgba(0, 200, 83, 52);
                border-radius: 16px;
                padding: 0;
                font-family: "{ui_font_family()}";
                font-size: 15px;
                font-weight: 600;
            }}
            QPushButton#topBarRefreshButton:hover {{
                background-color: rgba(0, 200, 83, 18);
                border-color: rgba(0, 200, 83, 94);
            }}
            QPushButton#topBarRefreshButton:pressed {{
                background-color: rgba(0, 178, 72, 32);
            }}
            QPushButton#topBarRefreshButton:disabled {{
                color: {PALETTE.disabled_text};
                border-color: rgba(95, 109, 106, 72);
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
        self.user_role_label.setStyleSheet(f"color: {with_alpha(PALETTE.accent_soft, 220).name()};")

    def _apply_refresh_icon(self) -> None:
        icon_paths = [
            Path(__file__).resolve().parents[2] / "assets" / "icon" / "refresh-ccw.png",
            Path(__file__).resolve().parents[1] / "assets" / "icon" / "refresh-ccw.png",
        ]
        for icon_path in icon_paths:
            if icon_path.exists():
                self.refresh_button.setIcon(QIcon(str(icon_path)))
                self.refresh_button.setIconSize(QSize(18, 18))
                self.refresh_button.setText("")
                return
        self.refresh_button.setText("↻")

    def _build_user_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("topBarUserMenu")
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setStyleSheet(
            f"""
            QMenu#topBarUserMenu {{
                background-color: rgba(15, 15, 30, 246);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 16px;
                padding: 8px;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QMenu#topBarUserMenu::item {{
                padding: 9px 14px;
                border-radius: 10px;
                margin: 2px 0;
            }}
            QMenu#topBarUserMenu::item:selected {{
                background-color: rgba(0, 200, 83, 18);
                color: {PALETTE.text};
            }}
            QMenu#topBarUserMenu::separator {{
                height: 1px;
                margin: 6px 8px;
                background: rgba(255, 255, 255, 0.08);
            }}
            """
        )

        account_action = menu.addAction("Account")
        menu.addSeparator()
        logout_action = menu.addAction("Log Out")

        account_action.triggered.connect(self.account_requested.emit)
        logout_action.triggered.connect(self.logout_requested.emit)
        logout_action.setIconVisibleInMenu(False)
        return menu

    def _show_user_menu(self, event) -> None:
        del event
        menu_width = self._menu.sizeHint().width()
        anchor = self.user_container.mapToGlobal(self.user_container.rect().bottomRight())
        self._menu.popup(anchor - QPoint(menu_width, -8))

    def set_page_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)

    def set_search_placeholder(self, placeholder: str) -> None:
        self.search_input.setPlaceholderText(placeholder)

    def set_server_status(self, label: str, variant: str = "online") -> None:
        self.server_badge.setText(label.upper())
        self.server_badge.set_variant(variant)

    def set_user_display(self, display_name: str, user_id: Optional[str] = None) -> None:
        self.user_display_label.setText(display_name)
        self._avatar_username = display_name
        if user_id is not None:
            self._avatar_user_id = user_id
        self._update_avatar()

    def set_user_role(self, role_label: str) -> None:
        self.user_role_label.setText(role_label)
        self._avatar_global_role = role_label
        self._update_avatar()

    def _update_avatar(self) -> None:
        avatar_path = resolve_avatar_path(
            self._avatar_username,
            user_id=self._avatar_user_id,
            global_role=self._avatar_global_role,
        )
        pixmap = render_svg_avatar(avatar_path, QSize(34, 34))
        if pixmap is not None:
            self.user_initials.setPixmap(pixmap)
            self.user_initials.setText("")
            return

        display_name = self._avatar_username or self.user_display_label.text()
        initials = "".join(part[0] for part in display_name.split()[:2]).upper() if display_name else "--"
        self.user_initials.setPixmap(QPixmap())
        self.user_initials.setText(initials or "--")

    def set_refresh_visible(self, visible: bool) -> None:
        self.refresh_button.setVisible(visible)

    def set_refresh_enabled(self, enabled: bool) -> None:
        self.refresh_button.setEnabled(enabled)


__all__ = ["TopBar"]
