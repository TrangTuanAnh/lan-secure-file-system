"""Context menu popover for room member actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QPushButton, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font_family
from ui.widgets.modern_button import PALETTE


class MemberContextMenu(QFrame):
    """Floating context menu for member row actions (Set Role, Remove)."""

    set_role_clicked = Signal()
    remove_member_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("memberContextMenu")
        self.setFrameShape(QFrame.NoFrame)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.set_role_button = QPushButton("Set Role")
        self.set_role_button.setObjectName("memberContextAction")
        self.set_role_button.setCursor(Qt.PointingHandCursor)
        self.set_role_button.setMinimumWidth(154)
        self.set_role_button.clicked.connect(self.set_role_clicked.emit)
        layout.addWidget(self.set_role_button)

        self.remove_member_button = QPushButton("Remove Member")
        self.remove_member_button.setObjectName("memberContextActionDanger")
        self.remove_member_button.setCursor(Qt.PointingHandCursor)
        self.remove_member_button.setMinimumWidth(154)
        self.remove_member_button.clicked.connect(self.remove_member_clicked.emit)
        layout.addWidget(self.remove_member_button)

    def _apply_styles(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 88))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(
            f"""
            QFrame#memberContextMenu {{
                background-color: rgba(20, 20, 36, 248);
                border: 1px solid rgba(0, 200, 83, 34);
                border-radius: 12px;
            }}
            QPushButton#memberContextAction,
            QPushButton#memberContextActionDanger {{
                min-height: 34px;
                padding: 0 12px;
                text-align: left;
                color: {PALETTE.text};
                background-color: transparent;
                border: none;
                border-radius: 8px;
                font-family: "{ui_font_family()}";
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#memberContextAction:hover {{
                background-color: rgba(0, 200, 83, 0.12);
                color: #f4fff9;
            }}
            QPushButton#memberContextActionDanger {{
                color: #ff9d9d;
            }}
            QPushButton#memberContextActionDanger:hover {{
                background-color: rgba(255, 82, 82, 0.12);
                color: #ffd5d5;
            }}
            QPushButton#memberContextAction:disabled,
            QPushButton#memberContextActionDanger:disabled {{
                color: rgba(244, 255, 249, 0.34);
            }}
            """
        )
        self.setFont(app_font(10, 600))

    def set_actions_enabled(self, can_set_role: bool, can_remove: bool) -> None:
        """Enable/disable menu actions based on permissions."""
        self.set_role_button.setEnabled(can_set_role)
        self.remove_member_button.setEnabled(can_remove)

    def show_at_position(self, parent_pos: QPoint) -> None:
        """Show the menu at the specified global position."""
        self.adjustSize()
        self.move(parent_pos)
        self.show()
        self.raise_()
        self.setFocus()

    def hide_menu(self) -> None:
        """Hide the context menu."""
        self.hide()

    def contains_global_pos(self, global_pos) -> bool:
        if not self.isVisible():
            return False
        return self.rect().contains(self.mapFromGlobal(global_pos))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide_menu()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["MemberContextMenu"]
