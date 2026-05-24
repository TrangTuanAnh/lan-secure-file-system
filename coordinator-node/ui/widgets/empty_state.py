"""Reusable empty state component for dashboard and room screens."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, ModernButton


class EmptyState(QFrame):
    """Display a polished empty state with an optional action."""

    action_requested = Signal()

    def __init__(
        self,
        title: str = "Nothing here yet",
        message: str = "",
        action_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyStateTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setFont(app_font(14, 700))
        layout.addWidget(self.title_label)

        self.message_label = QLabel(message or "No content is available in this section yet.")
        self.message_label.setObjectName("emptyStateMessage")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setFont(ui_font(10))
        layout.addWidget(self.message_label)

        self.action_button = ModernButton(action_text or "Take Action")
        self.action_button.setMinimumWidth(150)
        self.action_button.setVisible(bool(action_text))
        self.action_button.clicked.connect(self.action_requested.emit)
        layout.addWidget(self.action_button, 0, Qt.AlignCenter)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#emptyState {{
                background-color: rgba(15, 15, 30, 158);
                border: 1px dashed rgba(0, 200, 83, 72);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#emptyStateTitle {{
                color: #f4fff9;
            }}
            QLabel#emptyStateMessage {{
                color: #8aa39a;
            }}
            """
        )

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def set_action_text(self, action_text: str) -> None:
        self.action_button.setText(action_text)
        self.action_button.setVisible(bool(action_text))


__all__ = ["EmptyState"]
