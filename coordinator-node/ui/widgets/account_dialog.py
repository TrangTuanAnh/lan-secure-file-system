"""Reusable account profile dialog for authenticated dashboard sessions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, ModernButton


class AccountDialog(QDialog):
    """Show authenticated user profile data without backend-specific logic."""

    def __init__(
        self,
        username: str,
        email: str,
        user_id: str,
        global_role_label: str,
        change_password_supported: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._user_id = user_id.strip()
        self.setModal(True)
        self.setWindowTitle("Account Profile")
        self.setObjectName("accountDialog")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        title = QLabel("Account Profile")
        title.setObjectName("dialogTitle")
        title.setFont(app_font(16, 700))
        root.addWidget(title)

        subtitle = QLabel("Your authenticated session details from the coordinator.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setFont(ui_font(9))
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        profile_card = QFrame()
        profile_card.setObjectName("profileCard")
        card_layout = QVBoxLayout(profile_card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)
        card_layout.addWidget(self._profile_row("Username", username or "--"))
        card_layout.addWidget(self._profile_row("Email", email or "--"))
        card_layout.addWidget(self._profile_row("User ID", self._user_id or "--", selectable=True))
        card_layout.addWidget(self._profile_row("Global role", global_role_label or "--"))
        root.addWidget(profile_card)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(12)

        self.copy_user_id_button = ModernButton("Copy User ID")
        self.copy_user_id_button.clicked.connect(self._copy_user_id)
        self.copy_user_id_button.setEnabled(bool(self._user_id))
        actions.addWidget(self.copy_user_id_button)

        self.change_password_button = ModernButton("Change Password")
        self.change_password_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.change_password_button.setEnabled(change_password_supported)
        if not change_password_supported:
            self.change_password_button.setToolTip("Change password is not supported by backend yet.")
        actions.addWidget(self.change_password_button)

        actions.addStretch()

        close_button = ModernButton("Close")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self.setStyleSheet(
            f"""
            QDialog#accountDialog {{
                background-color: rgba(15, 15, 30, 246);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 24px;
            }}
            QFrame#profileCard {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 20px;
            }}
            QFrame#profileRow {{
                background-color: rgba(15, 15, 30, 168);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#dialogSubtitle,
            QLabel#rowKey {{
                color: #8aa39a;
            }}
            QLabel#rowValue {{
                color: #f4fff9;
            }}
            """
        )

    def _profile_row(self, label_text: str, value_text: str, selectable: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("profileRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        key_label = QLabel(label_text)
        key_label.setObjectName("rowKey")
        key_label.setFont(ui_font(9, 600))
        layout.addWidget(key_label, 0, Qt.AlignTop)

        value_label = QLabel(value_text)
        value_label.setObjectName("rowValue")
        value_label.setFont(app_font(10, 600))
        value_label.setWordWrap(True)
        if selectable:
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(value_label, 1)
        return row

    def _copy_user_id(self) -> None:
        if not self._user_id:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._user_id)


__all__ = ["AccountDialog"]
