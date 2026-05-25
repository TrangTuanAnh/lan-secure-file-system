"""Dashboard settings page with local preferences and account context."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.app_settings import DEFAULT_APP_SETTINGS
from ui.dashboard_runtime import DashboardRuntimeConfig
from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.modern_button import ModernButton, PALETTE
from ui.widgets.top_bar import TopBar


class _InfoRow(QFrame):
    """Small label/value row used by account and runtime sections."""

    def __init__(self, label: str, value: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsInfoRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        label_widget = QLabel(label, self)
        label_widget.setFont(ui_font(10, weight=600))
        label_widget.setMinimumWidth(170)
        layout.addWidget(label_widget)

        value_widget = QLabel(value if value else "-", self)
        value_widget.setFont(ui_font(10))
        value_widget.setWordWrap(True)
        value_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(value_widget, stretch=1)


class SettingsPage(QWidget):
    """Frontend-only dashboard settings rendered in the content area."""

    settings_changed = Signal(dict)
    logout_requested = Signal()

    def __init__(
        self,
        username: str = "",
        user_id: str = "",
        email: str = "",
        global_role: str = "USER",
        runtime: Optional[DashboardRuntimeConfig] = None,
        settings: Optional[dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._username = username
        self._user_id = user_id
        self._email = email
        self._global_role = global_role
        self._runtime = runtime or DashboardRuntimeConfig()
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
            subtitle="Configure preferences, review account context, and manage this session.",
            search_placeholder="Settings search is not available",
            user_display=self._username or "Authenticated User",
            show_refresh_button=False,
        )
        self.top_bar.search_input.hide()
        self.top_bar.set_user_role("Administrator" if self._global_role.upper() == "ADMIN" else "Secure Operator")
        root.addWidget(self.top_bar)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        content = QWidget(scroll)
        scroll_layout = QVBoxLayout(content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(18)

        cards_row = QGridLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setHorizontalSpacing(18)
        cards_row.setVerticalSpacing(18)

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
        scroll_layout.addLayout(cards_row)

        scroll_layout.addWidget(
            self._build_section(
                title="Account",
                description="Signed-in identity used by the dashboard.",
                rows=[
                    ("Username", self._username),
                    ("Email", self._email),
                    ("User ID", self._user_id),
                    ("Global role", self._global_role),
                ],
            )
        )
        scroll_layout.addWidget(
            self._build_section(
                title="Coordinator Connection",
                description="Runtime connection values currently used by this client.",
                rows=self._runtime_rows(),
            )
        )
        scroll_layout.addWidget(self._build_actions_section())
        scroll_layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self._wire_signals()

    def _build_card(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_label = QLabel(title, card)
        title_label.setObjectName("settingsCardTitle")
        title_label.setFont(app_font(14, 700))
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle, card)
        subtitle_label.setObjectName("settingsCardSubtitle")
        subtitle_label.setFont(ui_font(9))
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)
        return card, layout

    def _build_section(self, *, title: str, description: str, rows: list[tuple[str, str]]) -> QWidget:
        container = QFrame(self)
        container.setObjectName("settingsSection")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QLabel(title, container)
        header.setObjectName("settingsSectionTitle")
        header.setFont(app_font(14, 700))
        layout.addWidget(header)

        desc = QLabel(description, container)
        desc.setObjectName("settingsSectionSubtitle")
        desc.setFont(ui_font(9))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for idx, (label, value) in enumerate(rows):
            grid.addWidget(_InfoRow(label, value, container), idx, 0)
        layout.addLayout(grid)
        return container

    def _build_actions_section(self) -> QWidget:
        container = QFrame(self)
        container.setObjectName("settingsActions")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QLabel("Session", container)
        header.setObjectName("settingsSectionTitle")
        header.setFont(app_font(14, 700))
        layout.addWidget(header)

        desc = QLabel(
            "Log out of the current dashboard session and return to the authentication screen.",
            container,
        )
        desc.setObjectName("settingsSectionSubtitle")
        desc.setFont(ui_font(9))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        logout_btn = ModernButton("Log Out", parent=container, variant="danger")
        logout_btn.setMinimumWidth(180)
        logout_btn.clicked.connect(self.logout_requested.emit)
        button_row.addWidget(logout_btn)
        layout.addLayout(button_row)
        return container

    def _runtime_rows(self) -> list[tuple[str, str]]:
        return [
            ("Host", str(getattr(self._runtime, "host", "-"))),
            ("Port", str(getattr(self._runtime, "port", "-"))),
            ("Request timeout (s)", str(getattr(self._runtime, "timeout", "-"))),
            ("Socket timeout (s)", str(getattr(self._runtime, "socket_timeout", "-"))),
            ("Max retries", str(getattr(self._runtime, "max_retries", "-"))),
            ("Retry delay (s)", str(getattr(self._runtime, "retry_delay", "-"))),
        ]

    def _combo_box(self, options: list[str]) -> QComboBox:
        combo = QComboBox(self)
        combo.addItems(options)
        combo.setEditable(False)
        return combo

    def _toggle(self, label: str) -> QCheckBox:
        checkbox = QCheckBox(label, self)
        checkbox.setFont(ui_font(10, 500))
        return checkbox

    def _add_setting_row(self, parent_layout: QVBoxLayout, label_text: str, field: QWidget) -> None:
        row = QFrame(self)
        row.setObjectName("settingsRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        label = QLabel(label_text, row)
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
        auto_logout = str(security.get("auto_logout", "Never"))
        if self.auto_logout_combo.findText(auto_logout) < 0:
            self.auto_logout_combo.addItem(auto_logout)

        self._building = True
        self.reduce_glow_checkbox.setChecked(bool(appearance.get("reduce_glow_effects", False)))
        self.reduce_animations_checkbox.setChecked(bool(appearance.get("reduce_animations", False)))
        self.compact_layout_checkbox.setChecked(bool(appearance.get("compact_layout", False)))
        self.confirm_delete_checkbox.setChecked(bool(security.get("confirm_before_deleting_files", True)))
        self.warn_unscanned_checkbox.setChecked(bool(security.get("warn_before_downloading_unscanned_files", True)))
        self.auto_logout_combo.setCurrentText(auto_logout)
        self.hide_user_id_checkbox.setChecked(bool(security.get("hide_user_id_in_profile_by_default", False)))
        self._building = False
        self._settings = self.current_settings()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollArea QWidget {{
                background-color: transparent;
            }}
            QFrame#settingsCard,
            QFrame#settingsSection,
            QFrame#settingsActions,
            QFrame#settingsRow,
            QFrame#settingsInfoRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QFrame#settingsInfoRow,
            QFrame#settingsRow {{
                background-color: rgba(15, 15, 30, 132);
                border-radius: 14px;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#settingsCardTitle,
            QLabel#settingsSectionTitle {{
                color: #f4fff9;
            }}
            QLabel#settingsCardSubtitle,
            QLabel#settingsSectionSubtitle,
            QLabel#settingsFieldLabel {{
                color: #8aa39a;
            }}
            QComboBox {{
                background-color: rgba(15, 15, 30, 176);
                color: {PALETTE.text};
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 14px;
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
