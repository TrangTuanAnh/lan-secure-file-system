"""Application font manager for the PySide6 UI.

Usage:
    from ui.fonts import load_app_fonts, UI_FONT, BRAND_FONT, app_font, brand_font

    load_app_fonts()
    app.setFont(app_font(10))
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtGui import QFont, QFontDatabase


# ============================================================
# Font family names
# ============================================================

BRAND_FONT = "Goldman"
UI_FONT = "Inter"
FALLBACK_FONT = "Segoe UI"


# ============================================================
# Font paths
# ============================================================

UI_DIR = Path(__file__).resolve().parent
FONT_DIR = UI_DIR / "assets" / "fonts"

GOLDMAN_DIR = FONT_DIR / "Goldman"
INTER_DIR = FONT_DIR / "Inter"


GOLDMAN_FONT_FILES = [
    GOLDMAN_DIR / "Goldman-Regular.ttf",
    GOLDMAN_DIR / "Goldman-Bold.ttf",
]

INTER_FONT_FILES = [
    INTER_DIR / "Inter_18pt-Regular.ttf",
    INTER_DIR / "Inter_18pt-Medium.ttf",
    INTER_DIR / "Inter_18pt-SemiBold.ttf",
    INTER_DIR / "Inter_18pt-Bold.ttf",
]


_loaded = False


# ============================================================
# Internal helpers
# ============================================================

def _load_font_files(font_files: Iterable[Path]) -> list[str]:
    """Load font files and return successfully registered font families."""
    loaded_families: list[str] = []

    for font_path in font_files:
        if not font_path.exists():
            print(f"[FontManager] Missing font file: {font_path}")
            continue

        font_id = QFontDatabase.addApplicationFont(str(font_path))

        if font_id == -1:
            print(f"[FontManager] Failed to load font: {font_path}")
            continue

        families = QFontDatabase.applicationFontFamilies(font_id)
        loaded_families.extend(families)

    return loaded_families


def _font_available(family: str) -> bool:
    """Check whether a font family is available after loading."""
    return family in QFontDatabase.families()


def _normalize_weight(weight: int | QFont.Weight) -> QFont.Weight:
    """Accept integer weights from app code and convert them to Qt enum values."""
    if isinstance(weight, QFont.Weight):
        return weight

    known_weights = {
        100: QFont.Weight.Thin,
        200: QFont.Weight.ExtraLight,
        300: QFont.Weight.Light,
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
        900: QFont.Weight.Black,
    }
    if weight in known_weights:
        return known_weights[weight]

    nearest = min(known_weights, key=lambda value: abs(value - int(weight)))
    return known_weights[nearest]


# ============================================================
# Public API
# ============================================================

def load_app_fonts() -> None:
    """Load all custom application fonts once.

    Safe to call multiple times.
    """
    global _loaded

    if _loaded:
        return

    loaded_goldman = _load_font_files(GOLDMAN_FONT_FILES)
    loaded_inter = _load_font_files(INTER_FONT_FILES)

    if not loaded_goldman:
        print("[FontManager] Goldman font not loaded. Falling back where needed.")

    if not loaded_inter:
        print("[FontManager] Inter font not loaded. Falling back where needed.")

    _loaded = True


def resolve_font_family(preferred: str, fallback: str = FALLBACK_FONT) -> str:
    """Return preferred font if available, otherwise fallback."""
    if _font_available(preferred):
        return preferred

    if _font_available(fallback):
        return fallback

    return "Arial"


def ui_font(
    size: int = 10,
    weight: int | QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """Create a normal UI font using Inter with fallback."""
    font = QFont(resolve_font_family(UI_FONT))
    font.setPointSize(size)
    font.setWeight(_normalize_weight(weight))
    return font


def brand_font(
    size: int = 24,
    weight: int | QFont.Weight = QFont.Weight.Bold,
) -> QFont:
    """Create a brand/title font using Goldman with fallback."""
    font = QFont(resolve_font_family(BRAND_FONT, UI_FONT))
    font.setPointSize(size)
    font.setWeight(_normalize_weight(weight))
    return font


def app_font(
    size: int = 10,
    weight: int | QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """Alias for default app-wide UI font."""
    return ui_font(size=size, weight=weight)


def ui_font_family() -> str:
    """Resolved UI font family name for stylesheet usage."""
    return resolve_font_family(UI_FONT)


def brand_font_family() -> str:
    """Resolved brand font family name for stylesheet usage."""
    return resolve_font_family(BRAND_FONT, UI_FONT)


__all__ = [
    "BRAND_FONT",
    "UI_FONT",
    "FALLBACK_FONT",
    "load_app_fonts",
    "resolve_font_family",
    "ui_font",
    "brand_font",
    "app_font",
    "ui_font_family",
    "brand_font_family",
]
