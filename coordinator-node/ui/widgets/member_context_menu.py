"""Context menu popover for room member actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QVBoxLayout, QWidget

from ui.fonts import app_font
from ui.widgets.modern_button import PALETTE, ModernButton


class MemberContextMenu(QFrame):
    """Floating context menu for member row actions (Set Role, Remove)."""

    set_role_clicked = Signal()
    remove_member_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("memberContextMenu")
        self.setFrameShape(QFrame.NoFrame)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.set_role_button = ModernButton("Set Role")
        self.set_role_button.setMinimumWidth(140)
        self.set_role_button.clicked.connect(self.set_role_clicked.emit)
        layout.addWidget(self.set_role_button)

        self.remove_member_button = ModernButton("Remove Member")
        self.remove_member_button.setMinimumWidth(140)
        self.remove_member_button.set_accent_color(PALETTE.error)
        self.remove_member_button.clicked.connect(self.remove_member_clicked.emit)
        layout.addWidget(self.remove_member_button)

    def _apply_styles(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(
            f"""
            QFrame#memberContextMenu {{
                background-color: rgba(20, 20, 36, 248);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 14px;
            }}
            """
        )

    def set_actions_enabled(self, can_set_role: bool, can_remove: bool) -> None:
        """Enable/disable menu actions based on permissions."""
        self.set_role_button.setEnabled(can_set_role)
        self.remove_member_button.setEnabled(can_remove)

    def show_at_position(self, global_pos: QPoint) -> None:
        """Show the menu at the specified global position."""
        self.move(global_pos)
        self.show()
        self.raise_()
        self.setFocus()

    def hide_menu(self) -> None:
        """Hide the context menu."""
        self.hide()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide_menu()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["MemberContextMenu"]
