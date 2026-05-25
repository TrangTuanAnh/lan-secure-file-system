"""Dashboard settings page with local JSON persistence."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from ui.app_settings import DEFAULT_APP_SETTINGS
from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE
from ui.widgets.top_bar import TopBar


class SettingsPage(QWidget):
    """Frontend-only dashboard settings rendered in the content area."""

    settings_changed = Signal(dict)

    def __init__(
        self,
        username: str = "",
        global_role: str = "USER",
        settings: Optional[dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._username = username
        self._global_role = global_role
        self._settings = settings or DEFAULT_APP_SETTINGS
        self._building = False
        self._build_ui()
        self._apply_styles()
        self.set_settings(self._settings)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        self.top_bar = TopBar(
            page_title="Settings",
            subtitle="Configure your local dashboard preferences and security prompts.",
            search_placeholder="Settings search is not available",
            user_display=self._username or "Authenticated User",
            show_refresh_button=False,
        )
        self.top_bar.search_input.hide()
        self.top_bar.set_user_role("Administrator" if self._global_role.upper() == "ADMIN" else "Secure Operator")
        root.addWidget(self.top_bar)

        cards_row = QGridLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setHorizontalSpacing(18)
        cards_row.setVerticalSpacing(18)
        root.addLayout(cards_row)

        appearance_card, appearance_layout = self._build_card(
            "Appearance",
            "Tune visual density and motion preferences for this desktop client.",
        )
        self.reduce_glow_checkbox = self._toggle("Reduce glow effects")
        self.reduce_animations_checkbox = self._toggle("Reduce animations")
        self.compact_layout_checkbox = self._toggle("Compact layout")
        appearance_layout.addWidget(self.reduce_glow_checkbox)
        appearance_layout.addWidget(self.reduce_animations_checkbox)
        appearance_layout.addWidget(self.compact_layout_checkbox)
        appearance_layout.addStretch()
        cards_row.addWidget(appearance_card, 0, 0)

        security_card, security_layout = self._build_card(
            "Security",
            "Manage frontend-only safety prompts for sensitive room operations.",
        )
        self.confirm_delete_checkbox = self._toggle("Confirm before deleting files")
        self.warn_unscanned_checkbox = self._toggle("Warn before downloading unscanned files")
        self.auto_logout_combo = self._combo_box(["Never", "15 minutes", "30 minutes", "60 minutes"])
        self.hide_user_id_checkbox = self._toggle("Hide User ID in profile by default")
        security_layout.addWidget(self.confirm_delete_checkbox)
        security_layout.addWidget(self.warn_unscanned_checkbox)
        self._add_setting_row(security_layout, "Auto logout", self.auto_logout_combo)
        security_layout.addWidget(self.hide_user_id_checkbox)
        security_layout.addStretch()
        cards_row.addWidget(security_card, 0, 1)

        cards_row.setColumnStretch(0, 1)
        cards_row.setColumnStretch(1, 1)

        self._wire_signals()

    def _build_card(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("settingsCardTitle")
        title_label.setFont(app_font(14, 700))
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("settingsCardSubtitle")
        subtitle_label.setFont(ui_font(9))
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)
        return card, layout

    def _combo_box(self, options: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(options)
        combo.setEditable(False)
        return combo

    def _toggle(self, label: str) -> QCheckBox:
        checkbox = QCheckBox(label)
        checkbox.setFont(ui_font(10, 500))
        return checkbox

    def _add_setting_row(self, parent_layout: QVBoxLayout, label_text: str, field: QWidget) -> None:
        row = QFrame()
        row.setObjectName("settingsRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setObjectName("settingsFieldLabel")
        label.setFont(ui_font(9, 600))
        layout.addWidget(label)
        layout.addWidget(field)
        parent_layout.addWidget(row)

    def _wire_signals(self) -> None:
        self.reduce_glow_checkbox.toggled.connect(self._emit_settings_changed)
        self.reduce_animations_checkbox.toggled.connect(self._emit_settings_changed)
        self.compact_layout_checkbox.toggled.connect(self._emit_settings_changed)
        self.confirm_delete_checkbox.toggled.connect(self._emit_settings_changed)
        self.warn_unscanned_checkbox.toggled.connect(self._emit_settings_changed)
        self.auto_logout_combo.currentTextChanged.connect(self._emit_settings_changed)
        self.hide_user_id_checkbox.toggled.connect(self._emit_settings_changed)

    def _emit_settings_changed(self) -> None:
        if self._building:
            return
        settings = self.current_settings()
        self._settings = settings
        self.settings_changed.emit(settings)

    def current_settings(self) -> dict[str, Any]:
        return {
            "appearance": {
                "reduce_glow_effects": self.reduce_glow_checkbox.isChecked(),
                "reduce_animations": self.reduce_animations_checkbox.isChecked(),
                "compact_layout": self.compact_layout_checkbox.isChecked(),
            },
            "security": {
                "confirm_before_deleting_files": self.confirm_delete_checkbox.isChecked(),
                "warn_before_downloading_unscanned_files": self.warn_unscanned_checkbox.isChecked(),
                "auto_logout": self.auto_logout_combo.currentText(),
                "hide_user_id_in_profile_by_default": self.hide_user_id_checkbox.isChecked(),
            },
        }

    def set_settings(self, settings: dict[str, Any]) -> None:
        merged = {
            **DEFAULT_APP_SETTINGS,
            **(settings or {}),
        }
        appearance = {**DEFAULT_APP_SETTINGS["appearance"], **merged.get("appearance", {})}
        security = {**DEFAULT_APP_SETTINGS["security"], **merged.get("security", {})}

        self._building = True
        self.reduce_glow_checkbox.setChecked(bool(appearance.get("reduce_glow_effects", False)))
        self.reduce_animations_checkbox.setChecked(bool(appearance.get("reduce_animations", False)))
        self.compact_layout_checkbox.setChecked(bool(appearance.get("compact_layout", False)))
        self.confirm_delete_checkbox.setChecked(bool(security.get("confirm_before_deleting_files", True)))
        self.warn_unscanned_checkbox.setChecked(bool(security.get("warn_before_downloading_unscanned_files", True)))
        self.auto_logout_combo.setCurrentText(str(security.get("auto_logout", "Never")))
        self.hide_user_id_checkbox.setChecked(bool(security.get("hide_user_id_in_profile_by_default", False)))
        self._building = False
        self._settings = self.current_settings()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#settingsCard,
            QFrame#settingsRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 22px;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#settingsCardTitle {{
                color: #f4fff9;
            }}
            QLabel#settingsCardSubtitle,
            QLabel#settingsFieldLabel {{
                color: #8aa39a;
            }}
            QComboBox {{
                background-color: rgba(15, 15, 30, 176);
                color: {PALETTE.text};
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
                padding: 10px 12px;
                min-height: 22px;
                font-family: "{ui_font_family()}";
            }}
            QComboBox:hover,
            QComboBox:focus {{
                border-color: rgba(0, 230, 118, 0.42);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 26px;
            }}
            QComboBox QAbstractItemView {{
                background-color: rgba(15, 15, 30, 246);
                color: {PALETTE.text};
                border: 1px solid rgba(0, 200, 83, 0.30);
                selection-background-color: rgba(0, 200, 83, 0.18);
                font-family: "{ui_font_family()}";
            }}
            QCheckBox {{
                color: {PALETTE.text};
                spacing: 10px;
                font-family: "{ui_font_family()}";
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                background-color: rgba(15, 15, 30, 176);
            }}
            QCheckBox::indicator:checked {{
                border-color: rgba(0, 230, 118, 0.60);
                background-color: rgba(0, 200, 83, 0.26);
            }}
            """
        )


__all__ = ["SettingsPage"]
