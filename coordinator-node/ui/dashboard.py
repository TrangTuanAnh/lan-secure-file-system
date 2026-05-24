"""Main dashboard window with sidebar routing and stacked content pages."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional


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
from ui.pages.room_page import RoomPage
from ui.widgets.account_drawer import AccountDrawer
from ui.widgets.app_shell import AppShell
from ui.widgets.modern_button import PALETTE


class DashboardWindow(QMainWindow):
    """Owns the fixed sidebar and switches central pages only."""

    logout_requested = Signal()
    room_open_requested = Signal(dict)

    def __init__(
        self,
        username: str = "",
        user_id: str = "",
        email: str = "",
        token: str = "",
        global_role: str = "USER",
        runtime: Optional[DashboardRuntimeConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._username = username
        self._user_id = user_id
        self._email = email
        self._token = token
        self._global_role = global_role
        self._runtime = runtime or DashboardRuntimeConfig()
        self._pages: dict[str, QWidget] = {}
        self._room_page: Optional[RoomPage] = None

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
        sidebar.set_user_info(
            self._username or "Authenticated User",
            self._email or "No email available",
            self._display_global_role(),
        )

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("dashboardPageStack")
        self.app_shell.add_content_widget(self.page_stack, 1)

        self.account_drawer = AccountDrawer(self)
        self.account_drawer.set_profile(
            self._username or "Authenticated User",
            self._email or "Not available",
            self._user_id or "",
            self._display_global_role(),
        )
        self.account_drawer.update_anchor_geometry()

        self.overview_page = OverviewPage(
            username=self._username,
            user_id=self._user_id,
            email=self._email,
            token=self._token,
            global_role=self._global_role,
            runtime=self._runtime,
        )
        self.my_rooms_page = MyRoomsPage(
            username=self._username,
            user_id=self._user_id,
            email=self._email,
            token=self._token,
            global_role=self._global_role,
            runtime=self._runtime,
        )

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
        self.overview_page.room_open_requested.connect(self._open_room_page)
        self.my_rooms_page.room_open_requested.connect(self._open_room_page)
        for page in (self.overview_page, self.my_rooms_page):
            page.top_bar.set_user_display(self._username or "Authenticated User")
            page.top_bar.set_user_role(self._display_global_role())
            page.top_bar.account_requested.connect(self._show_account_dialog)
            page.top_bar.settings_requested.connect(lambda: print("Settings requested"))
            page.top_bar.logout_requested.connect(self.logout_requested.emit)

    def _display_global_role(self) -> str:
        return "Administrator" if self._global_role.upper() == "ADMIN" else "Secure Operator"

    def _on_navigation_requested(self, item_id: str) -> None:
        self._show_page(item_id)

    def _show_page(self, item_id: str) -> None:
        page = self._pages.get(item_id)
        if page is None:
            return
        self.app_shell.sidebar_nav.set_current_item("rooms" if item_id == "room_page" else item_id)
        self.page_stack.setCurrentWidget(page)

    def _open_room_page(self, room_payload: dict[str, Any]) -> None:
        if self._room_page is not None:
            self.page_stack.removeWidget(self._room_page)
            self._room_page.deleteLater()
            self._room_page = None

        merged_payload = {
            **room_payload,
            "username": room_payload.get("username") or self._username,
            "email": room_payload.get("email") or self._email,
            "global_role": room_payload.get("global_role") or self._global_role,
            "current_username": room_payload.get("current_username") or self._username,
            "current_user_id": room_payload.get("current_user_id") or room_payload.get("user_id") or self._user_id,
        }
        self._room_page = RoomPage(
            room_data=merged_payload,
            username=self._username,
            user_id=self._user_id,
            email=self._email,
            token=self._token,
            global_role=self._global_role,
            runtime=self._runtime,
        )
        self._room_page.back_requested.connect(self._on_room_page_back_requested)
        self._room_page.top_bar.set_user_display(self._username or "Authenticated User")
        self._room_page.top_bar.set_user_role(self._display_global_role())
        self._room_page.top_bar.account_requested.connect(self._show_account_dialog)
        self._room_page.top_bar.settings_requested.connect(lambda: print("Settings requested"))
        self._room_page.top_bar.logout_requested.connect(self.logout_requested.emit)
        self.page_stack.addWidget(self._room_page)
        self._pages["room_page"] = self._room_page
        self.room_open_requested.emit(merged_payload)
        self._show_page("room_page")

    def _show_account_dialog(self) -> None:
        self.account_drawer.set_profile(
            self._username or "Authenticated User",
            self._email or "Not available",
            self._user_id or "",
            self._display_global_role(),
        )
        self.account_drawer.open()

    def _on_room_page_back_requested(self) -> None:
        self._show_page("rooms")
        self.my_rooms_page.reload_rooms()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "account_drawer"):
            self.account_drawer.update_anchor_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._show_page("overview")
        self.account_drawer.update_anchor_geometry()


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
