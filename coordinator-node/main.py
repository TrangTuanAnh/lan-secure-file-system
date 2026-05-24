"""Desktop application entry point and window router."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from ui.fonts import app_font, load_app_fonts
from ui.pages.dashboard_page import DashboardRuntimeConfig, DashboardWindow
from ui.pages.login_page import LoginRuntimeConfig, LoginWindow
from ui.pages.signup_page import SignupWindow


class AppController:
    """Routes authenticated users from login into the dashboard."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self.login_window: Optional[LoginWindow] = None
        self.signup_window: Optional[SignupWindow] = None
        self.dashboard_window: Optional[DashboardWindow] = None

    def start(self) -> None:
        self._show_login_window()

    def _show_login_window(self) -> None:
        """Show the original login window.

        Important: show login before closing signup so QApplication does not
        think the last visible window was closed and quit the app.
        """
        if self.login_window is None:
            self.login_window = LoginWindow()
            self.login_window.login_successful.connect(self._on_login_successful)
            self.login_window.signup_requested.connect(self._show_signup_window)

        self.login_window.show()
        self.login_window.raise_()
        self.login_window.activateWindow()

        if self.signup_window is not None:
            self.signup_window.close()
            self.signup_window = None

    def _show_signup_window(self) -> None:
        """Show signup while keeping the routed LoginWindow alive."""
        if self.signup_window is None:
            self.signup_window = SignupWindow()
            self.signup_window.back_to_login_requested.connect(self._show_login_window)

        self.signup_window.show()
        self.signup_window.raise_()
        self.signup_window.activateWindow()

        if self.login_window is not None:
            self.login_window.hide()

    def _on_login_successful(self, payload: dict) -> None:
        username = payload.get("username", "")
        token = payload.get("token", "")

        login_runtime = self.login_window._runtime if self.login_window is not None else LoginRuntimeConfig()
        dashboard_runtime = DashboardRuntimeConfig(
            host=login_runtime.host,
            port=login_runtime.port,
            timeout=login_runtime.timeout,
            socket_timeout=login_runtime.socket_timeout,
            max_retries=login_runtime.max_retries,
            retry_delay=login_runtime.retry_delay,
        )

        self.dashboard_window = DashboardWindow(
            username=username,
            token=token,
            runtime=dashboard_runtime,
        )
        self.dashboard_window.logout_requested.connect(self._on_dashboard_logout_requested)
        self.dashboard_window.show()

        if self.login_window is not None:
            self.login_window.hide()
        if self.signup_window is not None:
            self.signup_window.close()
            self.signup_window = None

    def _on_dashboard_logout_requested(self) -> None:
        if self.dashboard_window is not None:
            self.dashboard_window.close()
            self.dashboard_window = None
        self._show_login_window()


def main() -> None:
    """Run the desktop application with the login-first flow."""
    app = QApplication(sys.argv)
    # Prevent the app from quitting during routed transitions such as
    # Signup -> Back to login, where one window closes while another is shown.
    app.setQuitOnLastWindowClosed(False)

    load_app_fonts()
    app.setFont(app_font(10))

    controller = AppController(app)
    app.setProperty("app_controller", controller)
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
