"""Login page wired to reusable widgets and backend services."""

from __future__ import annotations

import sys
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from network.backend_client_sdk import BackendConfig
from config import APP_CONFIG
from services.services import BackendService
from ui.fonts import app_font, brand_font, load_app_fonts, ui_font_family
from ui.widgets.decorative_panel import DecorativePanel
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.modern_lineedit import ModernLineEdit


APP_FONT = "Inter"
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LoginRuntimeConfig:
    """Runtime settings for backend access."""

    host: str = APP_CONFIG.backend_host
    port: int = APP_CONFIG.backend_port
    timeout: int = APP_CONFIG.backend_timeout
    socket_timeout: int = APP_CONFIG.backend_socket_timeout
    max_retries: int = APP_CONFIG.backend_max_retries
    retry_delay: int = APP_CONFIG.backend_retry_delay

    def to_backend_config(self) -> BackendConfig:
        return BackendConfig(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            socket_timeout=self.socket_timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
        )


class BackendStartupWorker(QObject):
    """Connects to the backend once so the UI can reflect availability."""

    finished = Signal(bool, str)

    def __init__(self, config: BackendConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._config)
            connected = service.connect()
            if connected and service.health_check():
                self.finished.emit(True, "Coordinator Server Online")
            elif connected:
                self.finished.emit(False, "Connected but health check failed")
            else:
                self.finished.emit(False, "Coordinator Server Offline")
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.finished.emit(False, f"Startup connection failed: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class LoginWorker(QObject):
    """Performs authentication without blocking the UI thread."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, config: BackendConfig, username: str, password: str) -> None:
        super().__init__()
        self._config = config
        self._username = username
        self._password = password

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._config)
            if not service.connect():
                self.failure.emit("Cannot reach server. Please check if it is running.")
                return
            login_result = service._client.login(self._username, self._password)
            if login_result:
                user_payload = login_result.get("user") or {}
                logger.info(
                    "LOGIN response keys=%s user_exists=%s user_keys=%s",
                    sorted(login_result.keys()),
                    bool(user_payload),
                    sorted(user_payload.keys()) if isinstance(user_payload, dict) else [],
                )
                backend_username = str(user_payload.get("username") or self._username)
                backend_email = str(user_payload.get("email") or "")
                backend_user_id = str(user_payload.get("id") or user_payload.get("userId") or "")
                global_role = (
                    user_payload.get("globalRole")
                    or user_payload.get("global_role")
                    or user_payload.get("role")
                    or login_result.get("user", {}).get("globalRole")
                    or login_result.get("globalRole")
                    or login_result.get("global_role")
                    or login_result.get("role")
                    or login_result.get("userRole")
                    or ""
                )
                resolved_role = APP_CONFIG.resolve_global_role(backend_username, str(global_role))
                self.success.emit(
                    {
                        "user": {
                            "id": backend_user_id,
                            "username": backend_username,
                            "email": backend_email,
                            "globalRole": resolved_role,
                        },
                        "user_id": backend_user_id,
                        "username": backend_username,
                        "email": backend_email,
                        "token": service._client.get_token() or "",
                        "global_role": resolved_role,
                    }
                )
                logger.info(
                    "Resolved login profile username=%s has_email=%s has_user_id=%s role=%s",
                    backend_username,
                    bool(backend_email),
                    bool(backend_user_id),
                    resolved_role,
                )
            else:
                self.failure.emit("Invalid username or password.")
        except TimeoutError:
            self.failure.emit("Connection timed out. Please try again.")
        except ConnectionRefusedError:
            self.failure.emit(
                f"Connection refused. Is the server running on {APP_CONFIG.backend_host}:{APP_CONFIG.backend_port}?"
            )
        except Exception as exc:
            self.failure.emit(f"Login failed: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class LoginCard(QFrame):
    """Composable login form built from reusable widgets."""

    login_requested = Signal(str, str)
    signup_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("loginCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        self.login_error = ErrorLabel(parent=self)
        self._error_host: Optional[QWidget] = self

        layout = QVBoxLayout(self)
        layout.setContentsMargins(46, 44, 46, 44)
        layout.setSpacing(14)

        title = QLabel("LAN Secure File System")
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(brand_font(24))
        layout.addWidget(title)

        subtitle = QLabel("Enterprise-grade access for your secure workspace")
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(app_font(10))
        layout.addWidget(subtitle)

        layout.addSpacing(18)
        layout.addWidget(self._build_field_label("Username"))

        self.username_input = ModernLineEdit("Enter your username")
        layout.addWidget(self.username_input)

        layout.addWidget(self._build_field_label("Password"))
        self.password_input = ModernLineEdit("Enter your password")
        self.password_input.setEchoMode(ModernLineEdit.Password)
        layout.addWidget(self.password_input)

        self.remember_checkbox = QCheckBox("Remember me")
        self.remember_checkbox.setObjectName("rememberCheckbox")
        layout.addWidget(self.remember_checkbox)

        self.login_button = ModernButton("Sign In")
        layout.addWidget(self.login_button)

        signup_row = QHBoxLayout()
        signup_row.setContentsMargins(0, 0, 0, 0)
        signup_row.setSpacing(4)
        signup_prompt = QLabel("Don't have an account?")
        signup_prompt.setObjectName("mutedLabel")
        signup_row.addWidget(signup_prompt)

        self.signup_link = QPushButton("Sign up")
        self.signup_link.setObjectName("textLink")
        self.signup_link.setCursor(Qt.PointingHandCursor)
        self.signup_link.setFlat(True)
        signup_row.addWidget(self.signup_link)
        signup_row.addStretch()

        signup_container = QWidget()
        signup_container.setLayout(signup_row)
        layout.addWidget(signup_container, alignment=Qt.AlignCenter)

        layout.addSpacing(10)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)

        self.status_indicator = QLabel("●")
        self.status_indicator.setObjectName("statusIndicator")
        status_row.addWidget(self.status_indicator)

        self.status_text = QLabel("Checking server...")
        self.status_text.setObjectName("statusText")
        status_row.addWidget(self.status_text)
        status_row.addStretch()

        status_container = QWidget()
        status_container.setLayout(status_row)
        layout.addWidget(status_container)
        layout.addStretch()

        self.login_button.clicked.connect(self._emit_login_request)
        self.password_input.returnPressed.connect(self._emit_login_request)
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.signup_link.clicked.connect(self.signup_requested.emit)

    @staticmethod
    def _build_field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(app_font(10, 600))
        return label

    def _emit_login_request(self) -> None:
        self.login_requested.emit(
            self.username_input.text().strip(),
            self.password_input.text(),
        )

    def set_error_host(self, host: QWidget) -> None:
        self._error_host = host
        self.login_error.move_to_top_center(host)

    def set_server_status(self, online: bool, message: str) -> None:
        self.status_indicator.setStyleSheet(
            f"color: {PALETTE.accent_alt if online else PALETTE.error}; font-size: 14px;"
        )
        self.status_text.setText(message)
        self.status_text.setStyleSheet(
            f"color: {PALETTE.accent_soft if online else '#ff98a9'}; font-size: 11px; font-weight: 600;"
        )

    def set_login_loading(self, loading: bool) -> None:
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.remember_checkbox.setEnabled(not loading)
        self.signup_link.setEnabled(not loading)
        self.login_button.set_loading(loading, "Authenticating")

    def show_login_error(self, message: str) -> None:
        self.login_error.move_to_top_center(self._error_host)
        self.login_error.show_error(message)

    def hide_login_error(self) -> None:
        self.login_error.hide_error()


class LoginWindow(QMainWindow):
    """Main login window using the shared widget system.

    This window only emits navigation signals. The actual page switching is
    handled by main.AppController so every LoginWindow stays connected to the
    same router.
    """

    login_successful = Signal(dict)
    signup_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._runtime = LoginRuntimeConfig()
        self._backend_service = BackendService(self._runtime.to_backend_config())
        self._startup_thread: Optional[QThread] = None
        self._startup_worker: Optional[BackendStartupWorker] = None
        self._login_thread: Optional[QThread] = None
        self._login_worker: Optional[LoginWorker] = None

        self.setWindowTitle("LAN Secure File System - Login")
        self.setGeometry(100, 100, 1200, 700)
        self.setMinimumSize(QSize(1000, 600))

        self._build_ui()
        self._apply_window_theme()
        self._connect_signals()
        self._setup_fade_in()

        QTimer.singleShot(50, self._fade_in.start)
        QTimer.singleShot(120, self._connect_backend_on_startup)

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.decorative_panel = DecorativePanel()
        main_layout.addWidget(self.decorative_panel, 9)

        right_panel = QWidget()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(48, 36, 48, 36)
        right_layout.setAlignment(Qt.AlignCenter)

        self.login_card = LoginCard()
        right_layout.addWidget(self.login_card, alignment=Qt.AlignCenter)
        main_layout.addWidget(right_panel, 11)
        self._toast_host = self

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

        self.centralWidget().setStyleSheet(
            f"""
            QWidget {{
                color: {PALETTE.text};
            }}
            QWidget#centralWidget {{
                background-color: {PALETTE.background};
            }}
            QWidget#rightPanel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(26, 26, 46, 246),
                    stop:1 rgba(15, 15, 30, 255)
                );
            }}
            QFrame#loginCard {{
                background-color: rgba(26, 26, 46, 232);
                border: 1px solid rgba(0, 200, 83, 48);
                border-radius: 28px;
            }}
            QLabel {{
                background: transparent;
            }}
            QLabel#cardTitle {{
                color: {PALETTE.text};
                background: transparent;
                font-size: 29px;
                font-weight: 650;
                letter-spacing: 0.5px;
            }}
            QLabel#cardSubtitle {{
                color: #98afa7;
                background: transparent;
                font-size: 12px;
                line-height: 1.45em;
                padding: 2px 12px 0 12px;
            }}
            QLabel#fieldLabel {{
                color: #d7ede2;
                background: transparent;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.8px;
                text-transform: uppercase;
                padding: 4px 0 1px 2px;
            }}
            QLabel#mutedLabel {{
                color: {PALETTE.text_muted};
                background: transparent;
                font-size: 11px;
            }}
            QLabel#statusText {{
                color: #90a69e;
                background: transparent;
                font-size: 11px;
            }}
            QLabel#statusIndicator {{
                color: #5f6d6a;
                background: transparent;
                font-size: 14px;
            }}
            QPushButton#textLink {{
                background: transparent;
                color: {PALETTE.accent_alt};
                border: none;
                font-family: "{ui_font_family()}";
                font-size: 11px;
                font-weight: 600;
                text-decoration: underline;
                padding: 0;
            }}
            QPushButton#textLink:hover {{
                color: {PALETTE.accent_bright};
            }}
            QPushButton#textLink:disabled {{
                color: {PALETTE.disabled_text};
            }}
            QCheckBox#rememberCheckbox {{
                color: {PALETTE.text_muted};
                font-family: "{ui_font_family()}";
                font-size: 11px;
                spacing: 10px;
            }}
            QCheckBox#rememberCheckbox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(95, 109, 106, 140);
                background: rgba(15, 15, 30, 180);
            }}
            QCheckBox#rememberCheckbox::indicator:hover {{
                border: 1px solid rgba(0, 230, 118, 165);
            }}
            QCheckBox#rememberCheckbox::indicator:checked {{
                border: 1px solid rgba(0, 200, 83, 210);
                background: rgba(0, 178, 72, 210);
            }}
            """
        )

    def _setup_fade_in(self) -> None:
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_in.setDuration(420)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.login_card.set_error_host(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.login_card.login_error.move_to_top_center(self._toast_host)

    def _connect_signals(self) -> None:
        self.login_card.login_requested.connect(self._on_login_requested)
        self.login_card.signup_requested.connect(self._on_signup_requested)

    def _connect_backend_on_startup(self) -> None:
        if self._startup_thread and self._startup_thread.isRunning():
            return

        self._startup_thread = QThread(self)
        self._startup_worker = BackendStartupWorker(self._runtime.to_backend_config())
        self._startup_worker.moveToThread(self._startup_thread)
        self._startup_thread.started.connect(self._startup_worker.run)
        self._startup_worker.finished.connect(self._on_backend_startup_finished)
        self._startup_worker.finished.connect(self._startup_thread.quit)
        self._startup_thread.finished.connect(self._startup_thread.deleteLater)
        self._startup_thread.finished.connect(self._startup_worker.deleteLater)
        self._startup_thread.finished.connect(self._cleanup_startup_thread)
        self._startup_thread.start()

    def _on_backend_startup_finished(self, online: bool, message: str) -> None:
        self.login_card.set_server_status(online, message)

    def _on_login_requested(self, username: str, password: str) -> None:
        validation_error = self._validate_login_inputs(username, password)
        if validation_error:
            self.login_card.show_login_error(validation_error)
            return

        self.login_card.hide_login_error()
        self.login_card.set_login_loading(True)
        self._start_login_worker(username, password)

    def _validate_login_inputs(self, username: str, password: str) -> Optional[str]:
        if not username:
            self.login_card.username_input.setFocus()
            return "Please enter your username."
        if not password:
            self.login_card.password_input.setFocus()
            return "Please enter your password."
        if len(password) < 6:
            self.login_card.password_input.setFocus()
            return "Password must be at least 6 characters."
        return None

    def _start_login_worker(self, username: str, password: str) -> None:
        if self._login_thread and self._login_thread.isRunning():
            return

        self._login_thread = QThread(self)
        self._login_worker = LoginWorker(
            self._runtime.to_backend_config(),
            username,
            password,
        )
        self._login_worker.moveToThread(self._login_thread)
        self._login_thread.started.connect(self._login_worker.run)
        self._login_worker.success.connect(self._on_login_success)
        self._login_worker.failure.connect(self._on_login_failed)
        self._login_worker.success.connect(self._login_thread.quit)
        self._login_worker.failure.connect(self._login_thread.quit)
        self._login_thread.finished.connect(self._login_thread.deleteLater)
        self._login_thread.finished.connect(self._login_worker.deleteLater)
        self._login_thread.finished.connect(self._cleanup_login_thread)
        self._login_thread.start()

    def _on_login_success(self, payload: Dict[str, Any]) -> None:
        self.login_card.set_login_loading(False)
        username = payload.get("username", "unknown")
        print(f"Login successful for user: {username}")
        print(f"Remember me: {self.login_card.remember_checkbox.isChecked()}")
        self.login_successful.emit(payload)

    def _on_login_failed(self, message: str) -> None:
        self.login_card.set_login_loading(False)
        self.login_card.show_login_error(message)

    def _on_signup_requested(self) -> None:
        # Navigation is handled by main.AppController.
        # Do not create SignupWindow here, otherwise the new windows will not be
        # connected to the app router.
        self.signup_requested.emit()

    def _cleanup_startup_thread(self) -> None:
        """Release references after the startup worker thread finishes.

        QThread.deleteLater() deletes the underlying C++ object, so keeping the
        old Python reference can make closeEvent crash when calling isRunning().
        """
        self._startup_thread = None
        self._startup_worker = None

    def _cleanup_login_thread(self) -> None:
        """Release references after the login worker thread finishes."""
        self._login_thread = None
        self._login_worker = None

    def _stop_thread_safely(self, thread_name: str) -> None:
        """Stop a QThread reference without crashing if Qt already deleted it."""
        thread = getattr(self, thread_name, None)
        try:
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            # The C++ QThread may already be deleted by deleteLater().
            pass
        finally:
            setattr(self, thread_name, None)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_thread_safely("_startup_thread")
        self._stop_thread_safely("_login_thread")

        if hasattr(self, "decorative_panel") and hasattr(self.decorative_panel, "stop_animation"):
            try:
                self.decorative_panel.stop_animation()
            except Exception:
                pass

        try:
            if self._backend_service.is_connected():
                self._backend_service.disconnect()
        except Exception:
            pass

        super().closeEvent(event)


def main() -> None:
    """Run the login page as a standalone desktop entry point."""
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    login_window = LoginWindow()
    login_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
