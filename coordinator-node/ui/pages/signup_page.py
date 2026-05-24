"""Signup page mirroring the login page architecture and design language."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
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

from services.services import BackendService
from config import APP_CONFIG
from ui.fonts import app_font, brand_font, load_app_fonts, ui_font_family
from ui.pages.login_page import BackendStartupWorker, LoginRuntimeConfig
from ui.widgets.decorative_panel import DecorativePanel
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.modern_lineedit import ModernLineEdit


class SignupWorker(QObject):
    """Performs signup without blocking the UI thread."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, runtime: LoginRuntimeConfig, username: str, email: str, password: str) -> None:
        super().__init__()
        self._config = runtime.to_backend_config()
        self._username = username
        self._email = email
        self._password = password

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._config)
            if not service.connect():
                self.failure.emit("Cannot reach server. Please check if it is running.")
                return
            if service.auth.signup(self._username, self._email, self._password):
                self.success.emit({"username": self._username, "email": self._email})
            else:
                self.failure.emit("Signup failed. Username or email may already exist.")
        except TimeoutError:
            self.failure.emit("Connection timed out. Please try again.")
        except ConnectionRefusedError:
            self.failure.emit(
                f"Connection refused. Is the server running on {APP_CONFIG.backend_host}:{APP_CONFIG.backend_port}?"
            )
        except Exception as exc:
            self.failure.emit(f"Signup failed: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class SignupCard(QFrame):
    """Signup form reusing the same visual system as the login card."""

    signup_requested = Signal(str, str, str, str)
    back_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("loginCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        self.signup_error = ErrorLabel(parent=self)
        self._error_host: Optional[QWidget] = self

        layout = QVBoxLayout(self)
        layout.setContentsMargins(46, 32, 46, 32)
        layout.setSpacing(10)

        title = QLabel("LAN Secure File System")
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(brand_font(24))
        layout.addWidget(title)

        subtitle = QLabel("Create your secure workspace account")
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(app_font(10))
        layout.addWidget(subtitle)

        layout.addSpacing(10)
        layout.addWidget(self._build_field_label("Username"))
        self.username_input = ModernLineEdit("Choose a username")
        layout.addWidget(self.username_input)

        layout.addWidget(self._build_field_label("Email"))
        self.email_input = ModernLineEdit("Enter your email address")
        layout.addWidget(self.email_input)

        layout.addWidget(self._build_field_label("Password"))
        self.password_input = ModernLineEdit("Create a password")
        self.password_input.setEchoMode(ModernLineEdit.Password)
        layout.addWidget(self.password_input)

        layout.addWidget(self._build_field_label("Confirm Password"))
        self.confirm_password_input = ModernLineEdit("Confirm your password")
        self.confirm_password_input.setEchoMode(ModernLineEdit.Password)
        layout.addWidget(self.confirm_password_input)

        self.create_account_button = ModernButton("Create Account")
        layout.addWidget(self.create_account_button)

        back_row = QHBoxLayout()
        back_row.setContentsMargins(0, 0, 0, 0)
        back_row.setSpacing(4)
        back_prompt = QLabel("Already have an account?")
        back_prompt.setObjectName("mutedLabel")
        back_row.addWidget(back_prompt)

        self.back_to_login_link = QPushButton("Back to login")
        self.back_to_login_link.setObjectName("textLink")
        self.back_to_login_link.setCursor(Qt.PointingHandCursor)
        self.back_to_login_link.setFlat(True)
        back_row.addWidget(self.back_to_login_link)
        back_row.addStretch()

        back_container = QWidget()
        back_container.setLayout(back_row)
        layout.addWidget(back_container, alignment=Qt.AlignCenter)

        layout.addSpacing(6)
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

        self.create_account_button.clicked.connect(self._emit_signup_request)
        self.confirm_password_input.returnPressed.connect(self._emit_signup_request)
        self.username_input.returnPressed.connect(self.email_input.setFocus)
        self.email_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.confirm_password_input.setFocus)
        self.back_to_login_link.clicked.connect(self.back_requested.emit)

    @staticmethod
    def _build_field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(app_font(10, 600))
        return label

    def _emit_signup_request(self) -> None:
        self.signup_requested.emit(
            self.username_input.text().strip(),
            self.email_input.text().strip(),
            self.password_input.text(),
            self.confirm_password_input.text(),
        )

    def set_error_host(self, host: QWidget) -> None:
        self._error_host = host
        self.signup_error.move_to_top_center(host)

    def set_server_status(self, online: bool, message: str) -> None:
        self.status_indicator.setStyleSheet(
            f"color: {PALETTE.accent_alt if online else PALETTE.error}; font-size: 14px;"
        )
        self.status_text.setText(message)
        self.status_text.setStyleSheet(
            f"color: {PALETTE.accent_soft if online else '#ff98a9'}; font-size: 11px; font-weight: 600;"
        )

    def set_signup_loading(self, loading: bool) -> None:
        self.username_input.setEnabled(not loading)
        self.email_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.confirm_password_input.setEnabled(not loading)
        self.back_to_login_link.setEnabled(not loading)
        self.create_account_button.set_loading(loading, "Creating Account")

    def show_signup_error(self, message: str) -> None:
        self.signup_error.move_to_top_center(self._error_host)
        self.signup_error.show_error(message)

    def hide_signup_error(self) -> None:
        self.signup_error.hide_error()


class SignupWindow(QMainWindow):
    """Main signup window reusing the login layout and theme.

    This page emits navigation signals only. main.AppController decides which
    window should be shown next.
    """

    back_to_login_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._runtime = LoginRuntimeConfig()
        self._backend_service = BackendService(self._runtime.to_backend_config())
        self._startup_thread: Optional[QThread] = None
        self._startup_worker: Optional[BackendStartupWorker] = None
        self._signup_thread: Optional[QThread] = None
        self._signup_worker: Optional[SignupWorker] = None

        self.setWindowTitle("LAN Secure File System - Sign Up")
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

        self.signup_card = SignupCard()
        right_layout.addWidget(self.signup_card, alignment=Qt.AlignCenter)
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
        self.signup_card.set_error_host(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.signup_card.signup_error.move_to_top_center(self._toast_host)

    def _connect_signals(self) -> None:
        self.signup_card.signup_requested.connect(self._on_signup_requested)
        self.signup_card.back_requested.connect(self._on_back_requested)

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
        self._startup_thread.start()

    def _on_backend_startup_finished(self, online: bool, message: str) -> None:
        self.signup_card.set_server_status(online, message)

    def _on_signup_requested(self, username: str, email: str, password: str, confirm_password: str) -> None:
        validation_error = self._validate_signup_inputs(username, email, password, confirm_password)
        if validation_error:
            self.signup_card.show_signup_error(validation_error)
            return

        self.signup_card.hide_signup_error()
        self.signup_card.set_signup_loading(True)
        self._start_signup_worker(username, email, password)

    def _validate_signup_inputs(
        self,
        username: str,
        email: str,
        password: str,
        confirm_password: str,
    ) -> Optional[str]:
        if not username:
            self.signup_card.username_input.setFocus()
            return "Please enter a username."
        if len(username) < 3:
            self.signup_card.username_input.setFocus()
            return "Username must be at least 3 characters."
        if not email:
            self.signup_card.email_input.setFocus()
            return "Please enter an email address."
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            self.signup_card.email_input.setFocus()
            return "Please enter a valid email address."
        if not password:
            self.signup_card.password_input.setFocus()
            return "Please enter a password."
        if len(password) < 6:
            self.signup_card.password_input.setFocus()
            return "Password must be at least 6 characters."
        if not confirm_password:
            self.signup_card.confirm_password_input.setFocus()
            return "Please confirm your password."
        if password != confirm_password:
            self.signup_card.confirm_password_input.setFocus()
            return "Passwords do not match."
        return None

    def _start_signup_worker(self, username: str, email: str, password: str) -> None:
        if self._signup_thread and self._signup_thread.isRunning():
            return

        self._signup_thread = QThread(self)
        self._signup_worker = SignupWorker(self._runtime, username, email, password)
        self._signup_worker.moveToThread(self._signup_thread)
        self._signup_thread.started.connect(self._signup_worker.run)
        self._signup_worker.success.connect(self._on_signup_success)
        self._signup_worker.failure.connect(self._on_signup_failed)
        self._signup_worker.success.connect(self._signup_thread.quit)
        self._signup_worker.failure.connect(self._signup_thread.quit)
        self._signup_thread.finished.connect(self._signup_thread.deleteLater)
        self._signup_thread.finished.connect(self._signup_worker.deleteLater)
        self._signup_thread.start()

    def _on_signup_success(self, payload: Dict[str, Any]) -> None:
        self.signup_card.set_signup_loading(False)
        print(f"Signup successful for user: {payload.get('username', 'unknown')}")
        self._on_back_requested()

    def _on_signup_failed(self, message: str) -> None:
        self.signup_card.set_signup_loading(False)
        self.signup_card.show_signup_error(message)

    def _on_back_requested(self) -> None:
        # Let main.AppController restore the original LoginWindow.
        # Creating a new LoginWindow here breaks the login_successful signal
        # connection and can make the app quit when this signup window closes.
        self.back_to_login_requested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._startup_thread and self._startup_thread.isRunning():
            self._startup_thread.quit()
            self._startup_thread.wait(2000)
        if self._signup_thread and self._signup_thread.isRunning():
            self._signup_thread.quit()
            self._signup_thread.wait(2000)
        if self._backend_service.is_connected():
            self._backend_service.disconnect()
        super().closeEvent(event)


def main() -> None:
    """Run the signup page as a standalone desktop entry point."""
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    signup_window = SignupWindow()
    signup_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
