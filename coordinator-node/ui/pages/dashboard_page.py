"""Compatibility wrapper for the dashboard overview page."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QMainWindow

from ui.fonts import app_font, load_app_fonts
from ui.pages.overview_page import OverviewPage


def main() -> None:
    """Run the overview content standalone for local UI inspection."""
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    window = QMainWindow()
    window.setWindowTitle("LAN Secure File System - Overview")
    window.setCentralWidget(OverviewPage(username="Secure Operator"))
    window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


__all__ = ["OverviewPage"]
