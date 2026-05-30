"""Reusable dashboard sidebar navigation widget."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui.fonts import app_font, brand_font, brand_font_family, ui_font, ui_font_family
from ui.utils.avatar_resolver import render_svg_avatar, resolve_avatar_path
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
        self._avatar_username = "Security Operator"
        self._avatar_user_id = ""
        self._avatar_global_role = "USER"
        self._status_variant = "loading"
        self._status_progress: Optional[tuple[int, int]] = None
        self._status_hide_timer = QTimer(self)
        self._status_hide_timer.setSingleShot(True)
        self._status_hide_timer.timeout.connect(self.clear_status)

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

        identity_row = QHBoxLayout()
        identity_row.setContentsMargins(0, 0, 0, 0)
        identity_row.setSpacing(10)

        self.user_avatar_label = QLabel("--")
        self.user_avatar_label.setObjectName("sidebarUserAvatar")
        self.user_avatar_label.setAlignment(Qt.AlignCenter)
        self.user_avatar_label.setMinimumSize(42, 42)
        self.user_avatar_label.setMaximumSize(42, 42)
        self.user_avatar_label.setFont(app_font(11, 700))
        identity_row.addWidget(self.user_avatar_label)

        identity_text = QVBoxLayout()
        identity_text.setContentsMargins(0, 0, 0, 0)
        identity_text.setSpacing(3)

        self.user_name_label = QLabel("Security Operator")
        self.user_name_label.setFont(app_font(11, 600))
        identity_text.addWidget(self.user_name_label)

        self.user_email_label = QLabel("operator@coordinator.local")
        self.user_email_label.setFont(ui_font(9))
        identity_text.addWidget(self.user_email_label)

        identity_row.addLayout(identity_text, 1)
        user_layout.addLayout(identity_row)

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

        self.status_card = QFrame()
        self.status_card.setObjectName("sidebarStatusCard")
        upload_layout = QVBoxLayout(self.status_card)
        upload_layout.setContentsMargins(14, 14, 14, 14)
        upload_layout.setSpacing(10)

        self.status_label = QLabel("Scanning uploaded file...")
        self.status_label.setObjectName("sidebarStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setFont(app_font(9, 600))
        upload_layout.addWidget(self.status_label)

        self.status_bar = QProgressBar()
        self.status_bar.setObjectName("sidebarStatusBar")
        self.status_bar.setTextVisible(False)
        self.status_bar.setFixedHeight(6)
        self.status_bar.setRange(0, 0)
        upload_layout.addWidget(self.status_bar)

        self.status_card.hide()
        layout.addWidget(self.status_card)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#sidebarNav {{
                background-color: rgba(15, 15, 30, 244);
                border-right: 1px solid rgba(0, 200, 83, 32);
            }}
            QFrame#sidebarUserCard,
            QFrame#sidebarNavSection,
            QFrame#sidebarStatusCard {{
                background-color: rgba(26, 26, 46, 214);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 20px;
            }}
            QFrame#sidebarStatusCard[statusVariant="loading"] {{
                background-color: rgba(18, 22, 36, 236);
                border-color: rgba(0, 200, 83, 44);
            }}
            QFrame#sidebarStatusCard[statusVariant="success"] {{
                background-color: rgba(10, 44, 30, 230);
                border-color: rgba(0, 200, 83, 82);
            }}
            QFrame#sidebarStatusCard[statusVariant="error"] {{
                background-color: rgba(52, 18, 22, 232);
                border-color: rgba(255, 82, 82, 88);
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
                border-radius: 10px;
            }}
            QPushButton#sidebarNavButton:hover {{
                background-color: rgba(0, 200, 83, 14);
                border-color: rgba(0, 200, 83, 42);
            }}
            QPushButton#sidebarNavButton:checked {{
                color: #f4fff9;
                background-color: rgba(0, 200, 83, 18);
                border-color: rgba(0, 200, 83, 58);
            }}
            QProgressBar#sidebarStatusBar {{
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.03);
                border-radius: 3px;
            }}
            QProgressBar#sidebarStatusBar::chunk {{
                background-color: rgba(0, 200, 83, 110);
                border-radius: 3px;
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
        self.status_label.setStyleSheet("color: #d9eee2;")
        self.user_avatar_label.setStyleSheet(
            f"""
            color: {PALETTE.accent_bright};
            background-color: {with_alpha(PALETTE.accent_alt, 22).name()};
            border: 1px solid {with_alpha(PALETTE.accent_alt, 72).name()};
            border-radius: 21px;
            """
        )
        self._update_avatar()

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

    def set_user_info(self, name: str, email: str, role: str, user_id: str = "") -> None:
        self.user_name_label.setText(name)
        self.user_email_label.setText(email)
        self.user_role_label.setText(role)
        self._avatar_username = name
        self._avatar_user_id = user_id
        self._avatar_global_role = role
        self._update_avatar()

    def _update_avatar(self) -> None:
        avatar_path = resolve_avatar_path(
            self._avatar_username,
            user_id=self._avatar_user_id,
            global_role=self._avatar_global_role,
        )
        pixmap = render_svg_avatar(avatar_path, QSize(42, 42))
        if pixmap is not None:
            self.user_avatar_label.setPixmap(pixmap)
            self.user_avatar_label.setText("")
            return

        self.user_avatar_label.setPixmap(QPixmap())
        initials = "".join(part[0] for part in self._avatar_username.split()[:2]).upper()
        self.user_avatar_label.setText(initials or "--")

    def _emit_navigation_requested(self, button_id: int) -> None:
        if 0 <= button_id < len(self._button_ids):
            self.navigation_requested.emit(self._button_ids[button_id])

    def _apply_status_variant(self, variant: str) -> None:
        self._status_variant = variant
        self.status_card.setProperty("statusVariant", variant)
        style = self.style()
        style.unpolish(self.status_card)
        style.polish(self.status_card)
        if variant == "error":
            self.status_label.setStyleSheet("color: #ffd6d6;")
        else:
            self.status_label.setStyleSheet("color: #d9eee2;")

    def set_status(self, variant: str, message: str, auto_hide_ms: int = 0) -> None:
        if not message.strip():
            self.clear_status()
            return
        self._status_hide_timer.stop()
        self.status_card.show()
        self.status_label.setText(message.strip())
        self._apply_status_variant(variant)
        is_loading = variant == "loading"
        self.status_bar.setVisible(is_loading)
        if is_loading:
            self._apply_progress_state()
        if auto_hide_ms > 0 and not is_loading:
            self._status_hide_timer.start(auto_hide_ms)

    def _apply_progress_state(self) -> None:
        if not self._status_progress:
            self.status_bar.setRange(0, 0)
            self.status_bar.setValue(0)
            return

        current, total = self._status_progress
        safe_total = max(1, total)
        safe_current = max(0, min(current, safe_total))
        self.status_bar.setRange(0, safe_total)
        self.status_bar.setValue(safe_current)

    def show_loading(self, message: str = "Scanning uploaded file...") -> None:
        self.set_status("loading", message or "Scanning uploaded file...")

    def show_success(self, message: str, auto_hide_ms: int = 4200) -> None:
        self.set_status("success", message, auto_hide_ms=auto_hide_ms)

    def show_error(self, message: str, auto_hide_ms: int = 5200) -> None:
        self.set_status("error", message, auto_hide_ms=auto_hide_ms)

    def clear_status(self) -> None:
        self._status_hide_timer.stop()
        self._status_progress = None
        self.status_card.hide()
        self.status_label.clear()
        self.status_bar.hide()

    def set_upload_status(self, active: bool, message: str = "Scanning uploaded file...") -> None:
        if active:
            self.show_loading(message or "Scanning uploaded file...")
            return
        self.clear_status()

    def apply_status_payload(self, payload: dict) -> None:
        variant = str(payload.get("variant") or "loading").strip().lower()
        message = str(payload.get("message") or "").strip()
        auto_hide_ms = int(payload.get("auto_hide_ms") or 0)
        current = payload.get("current")
        total = payload.get("total")
        if current is not None and total is not None:
            try:
                self._status_progress = (int(current), int(total))
            except (TypeError, ValueError):
                self._status_progress = None
        elif variant in {"success", "error", "clear"}:
            self._status_progress = None
        if variant == "success":
            self.show_success(message, auto_hide_ms=auto_hide_ms or 4200)
            return
        if variant == "error":
            self.show_error(message, auto_hide_ms=auto_hide_ms or 5200)
            return
        if variant == "clear":
            self.clear_status()
            return
        self.show_loading(message or "Loading...")


__all__ = ["SidebarNav"]
