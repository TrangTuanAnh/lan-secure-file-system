"""Reusable dialog for creating secure rooms without backend coupling."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.modern_lineedit import ModernLineEdit


class CreateRoomDialog(QDialog):
    """Compact modal dialog for room creation requests."""

    create_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("createRoomDialog")
        self.setModal(True)
        self.setWindowTitle("Create Secure Room")
        self.setMinimumWidth(440)
        self.setSizeGripEnabled(False)

        self.error_label = ErrorLabel(parent=self)

        self._build_ui()
        self._apply_styles()
        self._setup_animations()

        QTimer.singleShot(30, self._fade_in.start)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Create Secure Room")
        title.setObjectName("dialogTitle")
        title.setFont(app_font(16, 700))
        layout.addWidget(title)

        subtitle = QLabel("Provision a protected workspace for encrypted collaboration.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setFont(ui_font(10))
        layout.addWidget(subtitle)

        field_label = QLabel("Room Name")
        field_label.setObjectName("fieldLabel")
        field_label.setFont(app_font(10, 600))
        layout.addWidget(field_label)

        self.room_name_input = ModernLineEdit("Enter a secure room name")
        self.room_name_input.returnPressed.connect(self._on_create_clicked)
        layout.addWidget(self.room_name_input)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 6, 0, 0)
        actions.setSpacing(12)

        self.cancel_button = ModernButton("Cancel")
        self.cancel_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)

        self.create_button = ModernButton("Create Room")
        self.create_button.clicked.connect(self._on_create_clicked)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog#createRoomDialog {{
                background-color: rgba(15, 15, 30, 248);
                border: 1px solid rgba(0, 200, 83, 52);
                border-radius: 24px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#dialogTitle {{
                color: #f4fff9;
            }}
            QLabel#dialogSubtitle {{
                color: #8aa39a;
            }}
            QLabel#fieldLabel {{
                color: #d7ede2;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.8px;
                text-transform: uppercase;
                padding-top: 2px;
            }}
            """
        )

    def _setup_animations(self) -> None:
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_in.setDuration(220)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_label.move_to_top_center(self)

    def _validate_name(self, room_name: str) -> Optional[str]:
        trimmed = room_name.strip()
        if not trimmed:
            self.room_name_input.setFocus()
            return "Please enter a room name."
        if len(trimmed) < 3:
            self.room_name_input.setFocus()
            return "Room name must be at least 3 characters."
        return None

    def _on_create_clicked(self) -> None:
        room_name = self.room_name_input.text()
        validation_error = self._validate_name(room_name)
        if validation_error:
            self.error_label.move_to_top_center(self)
            self.error_label.show_error(validation_error)
            return

        self.error_label.hide_error()
        self.create_requested.emit(room_name.strip())

    def set_loading(self, loading: bool) -> None:
        self.room_name_input.setEnabled(not loading)
        self.cancel_button.setEnabled(not loading)
        self.create_button.set_loading(loading, "Creating Room")


__all__ = ["CreateRoomDialog"]
