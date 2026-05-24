"""Reusable status badge for roles, connectivity, and state labels."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ui.fonts import ui_font, ui_font_family
from ui.widgets.modern_button import PALETTE, blend, to_color, with_alpha


class StatusBadge(QLabel):
    """Compact badge with reusable accent variants."""

    PRESET_COLORS = {
        "online": PALETTE.accent_alt,
        "offline": PALETTE.error,
        "owner": PALETTE.accent_bright,
        "member": PALETTE.accent_soft,
        "viewer": "#72d6ff",
        "active": PALETTE.accent_alt,
        "warning": "#ffb020",
    }

    def __init__(
        self,
        text: str = "",
        variant: str = "active",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._accent = QColor(PALETTE.accent_alt)

        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFont(ui_font(9, 600))
        self.setMinimumHeight(26)
        self.set_margin_padding()
        self.set_variant(variant)

    def set_margin_padding(self) -> None:
        self.setContentsMargins(0, 0, 0, 0)

    def set_variant(self, variant: str) -> None:
        """Apply a preset visual variant."""
        self._variant = variant
        accent = self.PRESET_COLORS.get(variant.lower(), PALETTE.accent_alt)
        self.set_accent_color(accent)

    def set_accent_color(self, color: QColor | str) -> None:
        """Set a custom accent color while preserving the badge style."""
        self._accent = to_color(color)
        text_color = blend(self._accent, PALETTE.text, 0.42).name()
        border_color = with_alpha(self._accent, 150).name(QColor.HexArgb)
        background = with_alpha(blend(self._accent, PALETTE.background, 0.78), 230).name(QColor.HexArgb)
        glow = with_alpha(self._accent, 42).name(QColor.HexArgb)
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {text_color};
                background-color: {background};
                border: 1px solid {border_color};
                border-radius: 13px;
                padding: 4px 10px;
                font-family: "{ui_font_family()}";
                font-size: 9px;
                font-weight: 600;
            }}
            QLabel:hover {{
                border-color: {with_alpha(self._accent, 200).name(QColor.HexArgb)};
                background-color: {with_alpha(blend(self._accent, glow, 0.35), 236).name(QColor.HexArgb)};
            }}
            """
        )


__all__ = ["StatusBadge"]
