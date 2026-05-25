"""Right-side account drawer for authenticated dashboard sessions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.utils.avatar_resolver import render_svg_avatar, resolve_avatar_path
from ui.widgets.modern_button import PALETTE, ModernButton


class AccountDrawer(QFrame):
    """Slide-out profile drawer rendered inside the dashboard window."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drawer_width = 392
        self._is_open = False
        self._animating = False
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.finished.connect(self._on_animation_finished)

        self._username = ""
        self._email = ""
        self._user_id = ""
        self._global_role = ""

        self.setObjectName("accountDrawer")
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        title = QLabel("Account Profile")
        title.setObjectName("drawerTitle")
        title.setFont(app_font(16, 700))
        top_row.addWidget(title, 1)

        self.close_button = ModernButton("Close")
        self.close_button.setMinimumWidth(92)
        self.close_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.close_button.clicked.connect(self.close_drawer)
        top_row.addWidget(self.close_button)
        root.addLayout(top_row)

        self.avatar_label = QLabel("A")
        self.avatar_label.setObjectName("drawerAvatar")
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setMinimumSize(72, 72)
        self.avatar_label.setMaximumSize(72, 72)
        self.avatar_label.setFont(app_font(26, 700))
        root.addWidget(self.avatar_label, 0, Qt.AlignLeft)

        self.name_label = QLabel("Authenticated User")
        self.name_label.setObjectName("drawerName")
        self.name_label.setFont(app_font(14, 700))
        root.addWidget(self.name_label)

        self.role_label = QLabel("Secure Operator")
        self.role_label.setObjectName("drawerRole")
        self.role_label.setFont(ui_font(9, 600))
        root.addWidget(self.role_label)

        self.profile_card = QFrame()
        self.profile_card.setObjectName("drawerProfileCard")
        card_layout = QVBoxLayout(self.profile_card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        self.email_value = self._profile_row(card_layout, "Email")
        self.user_id_value = self._profile_row(card_layout, "User ID", selectable=True)
        self.global_role_value = self._profile_row(card_layout, "Global role")
        root.addWidget(self.profile_card)

        root.addStretch()

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        self.copy_user_id_button = ModernButton("Copy User ID")
        self.copy_user_id_button.clicked.connect(self._copy_user_id)
        actions.addWidget(self.copy_user_id_button)
        actions.addStretch()
        root.addLayout(actions)

    def _profile_row(self, parent_layout: QVBoxLayout, label_text: str, selectable: bool = False) -> QLabel:
        row = QFrame()
        row.setObjectName("drawerProfileRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        key = QLabel(label_text)
        key.setObjectName("drawerKey")
        key.setFont(ui_font(8, 600))
        layout.addWidget(key)

        value = QLabel("Not available")
        value.setObjectName("drawerValue")
        value.setWordWrap(True)
        value.setFont(app_font(10, 600))
        if selectable:
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(value)
        parent_layout.addWidget(row)
        return value

    def _apply_styles(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(-2, 0)
        shadow.setColor(QColor(0, 200, 83, 34))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(
            f"""
            QFrame#accountDrawer {{
                background-color: rgba(15, 15, 30, 248);
                border: 1px solid rgba(0, 200, 83, 34);
                border-top-left-radius: 26px;
                border-bottom-left-radius: 26px;
            }}
            QFrame#drawerProfileCard,
            QFrame#drawerProfileRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#drawerAvatar {{
                color: {PALETTE.accent_bright};
                background-color: rgba(0, 200, 83, 12);
                border: none;
                border-radius: 36px;
            }}
            QLabel#drawerRole {{
                color: #8fd8b0;
            }}
            QLabel#drawerKey {{
                color: #8aa39a;
                text-transform: uppercase;
                letter-spacing: 0.6px;
            }}
            QLabel#drawerValue {{
                color: #f4fff9;
            }}
            """
        )

    def set_profile(
        self,
        username: str,
        email: str,
        user_id: str,
        global_role_label: str,
        hide_user_id: bool = False,
    ) -> None:
        self._username = username or "Authenticated User"
        self._email = email or ""
        self._user_id = user_id or ""
        self._global_role = global_role_label or "Secure Operator"

        self._update_avatar()
        self.name_label.setText(self._username)
        self.role_label.setText(self._global_role)
        self.email_value.setText(self._email or "Not available")
        if hide_user_id:
            self.user_id_value.setText("Hidden by preference")
        else:
            self.user_id_value.setText(self._user_id or "Not available")
        self.global_role_value.setText(self._global_role or "Not available")
        self.copy_user_id_button.setEnabled(bool(self._user_id) and not hide_user_id)

    def _update_avatar(self) -> None:
        avatar_path = resolve_avatar_path(
            self._username,
            user_id=self._user_id,
            global_role=self._global_role,
        )
        pixmap = render_svg_avatar(avatar_path, QSize(72, 72))
        if pixmap is not None:
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.setText("")
            return

        self.avatar_label.setPixmap(QPixmap())
        self.avatar_label.setText((self._username[:1] or "A").upper())

    def update_anchor_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        height = max(0, parent.height() - 24)
        open_rect = QRect(parent.width() - self._drawer_width - 12, 12, self._drawer_width, height)
        closed_rect = QRect(parent.width() + 12, 12, self._drawer_width, height)
        self.setGeometry(open_rect if self._is_open else closed_rect)

    def open(self) -> None:
        if self._is_open or self._animating:
            return
        self._animate(opening=True)

    def close_drawer(self) -> None:
        if not self._is_open or self._animating:
            return
        self._animate(opening=False)

    def _animate(self, opening: bool) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        height = max(0, parent.height() - 24)
        open_rect = QRect(parent.width() - self._drawer_width - 12, 12, self._drawer_width, height)
        closed_rect = QRect(parent.width() + 12, 12, self._drawer_width, height)

        self._animating = True
        self._is_open = opening
        self.show()
        self.raise_()
        self.setFocus()

        self._animation.stop()
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.OutCubic if opening else QEasingCurve.InCubic)
        self._animation.setStartValue(self.geometry() if self.isVisible() else closed_rect)
        self._animation.setEndValue(open_rect if opening else closed_rect)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        self._animating = False
        if not self._is_open:
            self.hide()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close_drawer()
            event.accept()
            return
        super().keyPressEvent(event)

    def _copy_user_id(self) -> None:
        if not self._user_id:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._user_id)


__all__ = ["AccountDrawer"]
