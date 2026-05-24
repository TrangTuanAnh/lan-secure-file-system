"""Main dashboard window with sidebar routing and stacked content pages."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ui.dashboard_runtime import DashboardRuntimeConfig
from ui.fonts import app_font, load_app_fonts
from ui.pages.my_rooms_page import MyRoomsPage
from ui.pages.overview_page import OverviewPage
from ui.widgets.app_shell import AppShell
from ui.widgets.modern_button import PALETTE


class DashboardWindow(QMainWindow):
    """Owns the fixed sidebar and switches central pages only."""

    logout_requested = Signal()
    room_open_requested = Signal(str)

    def __init__(
        self,
        username: str = "",
        token: str = "",
        runtime: Optional[DashboardRuntimeConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._username = username
        self._token = token
        self._runtime = runtime or DashboardRuntimeConfig()
        self._pages: dict[str, QWidget] = {}

        self.setWindowTitle("LAN Secure File System - Dashboard")
        self.setMinimumSize(QSize(1260, 760))
        self.resize(1360, 840)

        self._build_ui()
        self._apply_window_theme()
        self._connect_signals()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root = QVBoxLayout(central_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.app_shell = AppShell()
        root.addWidget(self.app_shell)

        sidebar = self.app_shell.sidebar_nav
        sidebar.add_nav_item("overview", "Overview", checked=True)
        sidebar.add_nav_item("rooms", "My Rooms")
        sidebar.set_user_info(self._username or "Authenticated User", "Session Active", "Secure Operator")

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("dashboardPageStack")
        self.app_shell.add_content_widget(self.page_stack, 1)

        self.overview_page = OverviewPage(username=self._username, token=self._token, runtime=self._runtime)
        self.my_rooms_page = MyRoomsPage(username=self._username, token=self._token, runtime=self._runtime)

        self._pages = {
            "overview": self.overview_page,
            "rooms": self.my_rooms_page,
        }
        self.page_stack.addWidget(self.overview_page)
        self.page_stack.addWidget(self.my_rooms_page)
        self.page_stack.setCurrentWidget(self.overview_page)

    def _apply_window_theme(self) -> None:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(PALETTE.background))
        palette.setColor(QPalette.WindowText, QColor(PALETTE.text))
        palette.setColor(QPalette.Base, QColor(PALETTE.surface))
        palette.setColor(QPalette.AlternateBase, QColor(PALETTE.surface_alt))
        palette.setColor(QPalette.Text, QColor(PALETTE.text))
        palette.setColor(QPalette.Button, QColor(PALETTE.surface))
        palette.setColor(QPalette.ButtonText, QColor(PALETTE.text))
        self.setPalette(palette)
        self.setFont(app_font(10))

    def _connect_signals(self) -> None:
        sidebar = self.app_shell.sidebar_nav
        sidebar.navigation_requested.connect(self._on_navigation_requested)
        sidebar.logout_requested.connect(self.logout_requested.emit)
        self.overview_page.room_open_requested.connect(self.room_open_requested.emit)
        self.my_rooms_page.room_open_requested.connect(self.room_open_requested.emit)
        self.overview_page.open_rooms_button.clicked.connect(lambda: self._show_page("rooms"))

    def _on_navigation_requested(self, item_id: str) -> None:
        self._show_page(item_id)

    def _show_page(self, item_id: str) -> None:
        page = self._pages.get(item_id)
        if page is None:
            return
        self.app_shell.sidebar_nav.set_current_item(item_id)
        self.page_stack.setCurrentWidget(page)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._show_page("overview")


def main() -> None:
    """Run the dashboard shell as a standalone desktop entry point."""
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    dashboard = DashboardWindow(username="Secure Operator", token="", runtime=DashboardRuntimeConfig())
    dashboard.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


__all__ = ["DashboardRuntimeConfig", "DashboardWindow"]
