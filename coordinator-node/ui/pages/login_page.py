"""
Modern PySide6 Login Page UI for LAN Secure File System
Featuring dark theme, green gradient accents, and smooth animations
Refactored with real backend integration, threading, and production UX
"""

import sys
import re
from typing import Optional, Dict, Any
from enum import Enum

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QCheckBox, QLabel, QFrame, QDialog,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize,
    Property, QRect, QPoint, QThread, Signal, QObject
)
from PySide6.QtGui import (
    QColor, QFont, QPalette, QPainter, QLinearGradient, QBrush, QPen
)
from PySide6.QtCore import QEvent

# Import real backend integration
from network.backend_client_sdk import BackendClient, BackendConfig
from services.services import BackendService


# ────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────

APP_FONT = "Segoe UI"
COLOR_DARK_BG = "#0f0f1e"
COLOR_DARK_CARD = "#1a1a2e"
COLOR_DARK_HOVER = "#222239"
COLOR_BORDER = "#333333"
COLOR_TEXT_PRIMARY = "#ffffff"
COLOR_TEXT_SECONDARY = "#a0a0a0"
COLOR_TEXT_MUTED = "#666666"
COLOR_GREEN_PRIMARY = "#00b248"
COLOR_GREEN_SECONDARY = "#00c853"
COLOR_GREEN_LIGHT = "#00e676"
COLOR_GREEN_ACCENT = "#00ff95"
COLOR_RED = "#ff1744"
COLOR_ERROR_BG = "#2a1520"
COLOR_ERROR_BORDER = "#ff1744"
COLOR_ERROR_TEXT = "#ff8a80"


class ButtonState(Enum):
    """Enum for button states"""
    NORMAL = 0
    HOVERED = 1
    PRESSED = 2
    LOADING = 3


# ────────────────────────────────────────────────────────────
# Background Workers (QThread-safe)
# ────────────────────────────────────────────────────────────

class ServerStatusWorker(QObject):
    """
    Worker that periodically checks server connectivity in a background thread.
    Emits status_changed with True (online) or False (offline).
    """
    status_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, host: str = "localhost", port: int = 8080):
        super().__init__()
        self._host = host
        self._port = port
        self._running = True

    def stop(self):
        """Stop the worker loop."""
        self._running = False

    def run(self):
        """Continuously check server status every 5 seconds."""
        while self._running:
            try:
                config = BackendConfig(host=self._host, port=self._port, timeout=5)
                client = BackendClient(config)
                client.connect()
                # If we get here, connection succeeded
                client.ping()
                client.disconnect()
                self.status_changed.emit(True)
            except Exception as e:
                self.status_changed.emit(False)
            # Wait 5 seconds before next check
            for _ in range(50):  # 50 * 0.1s = 5s, allows responsive stop
                if not self._running:
                    return
                QThread.msleep(100)


class LoginWorker(QObject):
    """
    Worker that performs login in a background thread.
    """
    login_success = Signal(dict)
    login_failed = Signal(str)

    def __init__(self, host: str, port: int, username: str, password: str):
        super().__init__()
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._service: Optional[BackendService] = None

    def run(self):
        """Execute login in background thread."""
        try:
            config = BackendConfig(host=self._host, port=self._port, timeout=15)
            self._service = BackendService(config)
            if not self._service.connect():
                self.login_failed.emit("Cannot reach server. Please check if the server is running.")
                return

            result = self._service.auth.login(self._username, self._password)
            if result:
                self.login_success.emit({"username": self._username})
            else:
                self.login_failed.emit("Invalid username or password.")
        except TimeoutError:
            self.login_failed.emit("Connection timed out. Server may be overloaded.")
        except ConnectionRefusedError:
            self.login_failed.emit("Connection refused. Is the server running on localhost:8080?")
        except ValueError as e:
            self.login_failed.emit(str(e) if str(e) else "Invalid credentials. Please try again.")
        except Exception as e:
            self.login_failed.emit(f"Login failed: {str(e)}")


class SignupWorker(QObject):
    """
    Worker that performs signup in a background thread.
    """
    signup_success = Signal(dict)
    signup_failed = Signal(str)

    def __init__(self, host: str, port: int, username: str, email: str, password: str):
        super().__init__()
        self._host = host
        self._port = port
        self._username = username
        self._email = email
        self._password = password
        self._service: Optional[BackendService] = None

    def run(self):
        """Execute signup in background thread."""
        try:
            config = BackendConfig(host=self._host, port=self._port, timeout=15)
            self._service = BackendService(config)
            if not self._service.connect():
                self.signup_failed.emit("Cannot reach server. Please check if the server is running.")
                return

            result = self._service.auth.signup(self._username, self._email, self._password)
            if result:
                self.signup_success.emit({"username": self._username, "email": self._email})
            else:
                self.signup_failed.emit("Registration failed. Username or email may already exist.")
        except TimeoutError:
            self.signup_failed.emit("Connection timed out. Server may be overloaded.")
        except ConnectionRefusedError:
            self.signup_failed.emit("Connection refused. Is the server running on localhost:8080?")
        except ValueError as e:
            self.signup_failed.emit(str(e) if str(e) else "Registration failed. Please try again.")
        except Exception as e:
            self.signup_failed.emit(f"Signup failed: {str(e)}")


# ────────────────────────────────────────────────────────────
# DecorativePanel — animated gradient left panel
# ────────────────────────────────────────────────────────────

class DecorativePanel(QFrame):
    """Left side decorative panel with animated gradient background"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(400)
        self.animation_progress = 0.0

        # Setup animation
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_timer.start(50)

    def _update_animation(self):
        """Update gradient animation"""
        self.animation_progress = (self.animation_progress + 0.01) % 1.0
        self.update()

    def paintEvent(self, event):
        """Paint the decorative background with animated gradient"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Main background gradient
        rect = self.rect()
        gradient = QLinearGradient(0, 0, rect.width(), rect.height())

        # Dark theme with subtle green accents
        gradient.setColorAt(0.0, QColor("#0a0e27"))      # Deep dark blue
        gradient.setColorAt(0.5, QColor("#0d1b2a"))      # Dark navy
        gradient.setColorAt(1.0, QColor("#0a0e27"))      # Back to deep dark

        painter.fillRect(rect, gradient)

        # Add subtle animated overlay with green accents
        overlay_gradient = QLinearGradient(
            0, 0 + (self.animation_progress * 100),
            0, rect.height() + (self.animation_progress * 100)
        )
        overlay_gradient.setColorAt(0.0, QColor(0, 200, 83, 0))      # Transparent green
        overlay_gradient.setColorAt(0.5, QColor(0, 200, 83, 10))     # Subtle green
        overlay_gradient.setColorAt(1.0, QColor(0, 200, 83, 0))      # Transparent

        painter.setOpacity(0.3)
        painter.fillRect(rect, overlay_gradient)

        painter.setOpacity(1.0)

        # Draw decorative circles with glow effect
        self._draw_decorative_elements(painter, rect)

    def _draw_decorative_elements(self, painter: QPainter, rect: QRect):
        """Draw decorative elements with glow"""
        positions = [
            (100, 100, 80),
            (150, 300, 120),
            (50, 500, 60),
            (200, 600, 100),
        ]

        for x, y, size in positions:
            # Glow effect (larger, more transparent circle)
            glow_gradient = QLinearGradient(x - size, y - size, x + size, y + size)
            glow_gradient.setColorAt(0.0, QColor(0, 200, 83, 20))
            glow_gradient.setColorAt(0.5, QColor(0, 200, 83, 5))
            glow_gradient.setColorAt(1.0, QColor(0, 200, 83, 0))

            painter.setBrush(glow_gradient)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(x, y), size + 20, size + 20)

            # Main circle
            circle_gradient = QLinearGradient(x - size, y - size, x + size, y + size)
            circle_gradient.setColorAt(0.0, QColor(0, 200, 83, 60))
            circle_gradient.setColorAt(1.0, QColor(0, 230, 118, 30))

            painter.setBrush(circle_gradient)
            painter.drawEllipse(QPoint(x, y), size, size)


# ────────────────────────────────────────────────────────────
# ModernLineEdit — focus-animated input
# ────────────────────────────────────────────────────────────

class ModernLineEdit(QLineEdit):
    """Custom line edit with focus animation and modern styling"""

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.is_focused = False
        self._focus_state = 0.0
        self.focus_animation = QPropertyAnimation(self, b"focus_state")
        self.focus_animation.setDuration(300)
        self.focus_animation.setEasingCurve(QEasingCurve.InOutQuad)

        self.setMinimumHeight(50)
        self.setCursorMoveStyle(Qt.LogicalMoveStyle)

    def _set_focus_state(self, value: float):
        self._focus_state = value
        self.update()

    def _get_focus_state(self) -> float:
        return self._focus_state

    focus_state = Property(float, _get_focus_state, _set_focus_state)

    def focusInEvent(self, event: QEvent):
        super().focusInEvent(event)
        self.is_focused = True
        self.focus_animation.setStartValue(0.0)
        self.focus_animation.setEndValue(1.0)
        self.focus_animation.start()

    def focusOutEvent(self, event: QEvent):
        super().focusOutEvent(event)
        self.is_focused = False
        self.focus_animation.setStartValue(self._focus_state)
        self.focus_animation.setEndValue(0.0)
        self.focus_animation.start()


# ────────────────────────────────────────────────────────────
# ErrorLabel — inline validation message
# ────────────────────────────────────────────────────────────

class ErrorLabel(QLabel):
    """Inline error message label with fade animation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            color: {COLOR_ERROR_TEXT};
            font-size: 10px;
            font-family: '{APP_FONT}';
            padding: 4px 0px;
        """)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.hide()

        # Fade animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    def show_error(self, message: str):
        """Show error with fade-in."""
        self.setText(message)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self.show()
        self._fade_anim.start()

    def hide_error(self):
        """Hide error with fade-out."""
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_finished, Qt.UniqueConnection)
        self._fade_anim.start()

    def _on_fade_out_finished(self):
        self.hide()


# ────────────────────────────────────────────────────────────
# ModernButton — premium gradient with glow & animations
# ────────────────────────────────────────────────────────────

class ModernButton(QPushButton):
    """Custom button with premium green gradient and smooth animations"""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.state = ButtonState.NORMAL
        self.is_loading = False
        self.loading_angle = 0

        self._hover_state = 0.0
        self._scale_factor = 1.0

        # Hover animation
        self.hover_animation = QPropertyAnimation(self, b"hover_state")
        self.hover_animation.setDuration(300)
        self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Scale animation
        self.scale_animation = QPropertyAnimation(self, b"scale_factor")
        self.scale_animation.setDuration(200)
        self.scale_animation.setEasingCurve(QEasingCurve.OutBack)



        # Loading animation
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self._update_loading)

        # Styling
        self.setMinimumHeight(52)
        self.setMinimumWidth(160)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def _set_hover_state(self, value: float):
        self._hover_state = value
        self.update()

    def _get_hover_state(self) -> float:
        return self._hover_state

    hover_state = Property(float, _get_hover_state, _set_hover_state)

    def _set_scale_factor(self, value: float):
        self._scale_factor = value
        self.update()

    def _get_scale_factor(self) -> float:
        return self._scale_factor

    scale_factor = Property(float, _get_scale_factor, _set_scale_factor)

    def _update_loading(self):
        """Update loading spinner angle"""
        self.loading_angle = (self.loading_angle + 30) % 360
        self.update()

    def set_loading(self, loading: bool):
        """Set button to loading state"""
        self.is_loading = loading
        self.setEnabled(not loading)

        if loading:
            self.loading_timer.start(50)
            self.state = ButtonState.LOADING
        else:
            self.loading_timer.stop()
            self.state = ButtonState.NORMAL

        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        if not self.is_loading:
            self.state = ButtonState.HOVERED
            self.hover_animation.setStartValue(self._hover_state)
            self.hover_animation.setEndValue(1.0)
            self.hover_animation.start()
            # Gentle scale up
            self.scale_animation.setStartValue(self._scale_factor)
            self.scale_animation.setEndValue(1.03)
            self.scale_animation.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self.is_loading:
            self.state = ButtonState.NORMAL
            self.hover_animation.setStartValue(self._hover_state)
            self.hover_animation.setEndValue(0.0)
            self.hover_animation.start()
            # Scale back
            self.scale_animation.setStartValue(self._scale_factor)
            self.scale_animation.setEndValue(1.0)
            self.scale_animation.start()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.is_loading:
            self.state = ButtonState.PRESSED
            self.scale_animation.setStartValue(self._scale_factor)
            self.scale_animation.setEndValue(0.97)
            self.scale_animation.setDuration(100)
            self.scale_animation.start()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self.is_loading:
            if self.underMouse():
                self.state = ButtonState.HOVERED
            else:
                self.state = ButtonState.NORMAL
            self.scale_animation.setStartValue(self._scale_factor)
            self.scale_animation.setEndValue(1.0)
            self.scale_animation.setDuration(200)
            self.scale_animation.start()

    def paintEvent(self, event):
        """Custom paint event for premium green gradient button with glow and shadow"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        corner_radius = 12

        # Apply scale transform
        if self._scale_factor != 1.0:
            center = rect.center()
            new_w = int(rect.width() * self._scale_factor)
            new_h = int(rect.height() * self._scale_factor)
            scaled_rect = QRect(
                center.x() - new_w // 2,
                center.y() - new_h // 2,
                new_w,
                new_h
            )
        else:
            scaled_rect = rect

        # Determine colors based on state
        if self.is_loading:
            start_color = QColor(COLOR_GREEN_PRIMARY)
            end_color = QColor(COLOR_GREEN_SECONDARY)
        else:
            progress = self._hover_state

            # Color palette: richer diagonal gradient
            # Normal: deeper green
            c1_n = QColor("#008837")
            c2_n = QColor(COLOR_GREEN_PRIMARY)
            c3_n = QColor(COLOR_GREEN_SECONDARY)

            # Hovered: brighter with accent
            c1_h = QColor(COLOR_GREEN_PRIMARY)
            c2_h = QColor(COLOR_GREEN_LIGHT)
            c3_h = QColor(COLOR_GREEN_ACCENT)

            def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
                return QColor(
                    int(a.red() + (b.red() - a.red()) * t),
                    int(a.green() + (b.green() - a.green()) * t),
                    int(a.blue() + (b.blue() - a.blue()) * t)
                )

            start_color = lerp_color(c1_n, c1_h, progress)
            mid_color = lerp_color(c2_n, c2_h, progress)
            end_color = lerp_color(c3_n, c3_h, progress)

        # ── Drop shadow ──
        if self._hover_state > 0.05:
            shadow_rect = scaled_rect.adjusted(1, 3, -1, 1)
            shadow_gradient = QLinearGradient(
                shadow_rect.topLeft(), shadow_rect.bottomRight()
            )
            shadow_alpha = int(80 * self._hover_state)
            shadow_gradient.setColorAt(0.0, QColor(0, 200, 83, shadow_alpha))
            shadow_gradient.setColorAt(0.5, QColor(0, 200, 83, int(shadow_alpha * 0.5)))
            shadow_gradient.setColorAt(1.0, QColor(0, 200, 83, 0))

            painter.setOpacity(0.6)
            painter.setBrush(shadow_gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(shadow_rect, corner_radius + 2, corner_radius + 2)
            painter.setOpacity(1.0)

        # ── Outer glow on hover ──
        if self._hover_state > 0.1:
            glow_rect = scaled_rect.adjusted(-3, -3, 3, 3)
            glow_gradient = QLinearGradient(glow_rect.topLeft(), glow_rect.bottomRight())
            glow_alpha = int(60 * self._hover_state)
            glow_gradient.setColorAt(0.0, QColor(0, 200, 83, glow_alpha))
            glow_gradient.setColorAt(0.5, QColor(0, 230, 118, int(glow_alpha * 0.4)))
            glow_gradient.setColorAt(1.0, QColor(0, 255, 149, 0))

            painter.setOpacity(0.4)
            painter.setBrush(glow_gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(glow_rect, corner_radius + 2, corner_radius + 2)
            painter.setOpacity(1.0)

        # ── Main button gradient (premium diagonal) ──
        gradient = QLinearGradient(
            scaled_rect.topLeft(), scaled_rect.bottomRight()
        )
        gradient.setColorAt(0.0, start_color)
        if not self.is_loading and self._hover_state > 0:
            gradient.setColorAt(0.5, mid_color)
        gradient.setColorAt(1.0, end_color)

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(scaled_rect, corner_radius, corner_radius)

        # ── Subtle inner highlight ──
        highlight_rect = scaled_rect.adjusted(2, 2, -2, -int(scaled_rect.height() * 0.6))
        if highlight_rect.height() > 10:
            hl_gradient = QLinearGradient(
                highlight_rect.topLeft(), highlight_rect.bottomLeft()
            )
            hl_gradient.setColorAt(0.0, QColor(255, 255, 255, 30))
            hl_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(hl_gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(highlight_rect, corner_radius - 2, corner_radius - 2)

        # ── Loading spinner ──
        if self.is_loading:
            self._draw_loading_spinner(painter, scaled_rect)

        # ── Text ──
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        font = QFont(APP_FONT, 12, QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(scaled_rect, Qt.AlignCenter, self.text())

    def _draw_loading_spinner(self, painter: QPainter, rect: QRect):
        """Draw rotating loading spinner"""
        center_x = rect.center().x()
        center_y = rect.center().y()
        radius = 10

        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.loading_angle)

        for i in range(12):
            painter.rotate(30)
            alpha = int(200 * (1 - i / 12))
            pen = QPen(QColor(255, 255, 255, alpha))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(0, radius, 0, radius + 6)

        painter.restore()


# ────────────────────────────────────────────────────────────
# SignupDialog — modal signup with backend integration
# ────────────────────────────────────────────────────────────

class SignupDialog(QDialog):
    """Modern modal signup dialog with real backend integration."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Create Account")
        self.setFixedSize(420, 520)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Fade-in effect
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(250)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self._build_ui()
        self._connect_signals()

    def showEvent(self, event):
        """Start fade-in animation when shown."""
        super().showEvent(event)
        self._fade_in.start()

    # ── UI Build ──

    def _build_ui(self):
        """Build the signup dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Card container
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_DARK_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 16px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(12)

        # Title
        title = QLabel("Create Account")
        title_font = QFont(APP_FONT, 22, QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; border: none;")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Join the secure file system")
        subtitle.setFont(QFont(APP_FONT, 10))
        subtitle.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; border: none;")
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)

        card_layout.addSpacing(16)

        # Username
        self._add_field_label(card_layout, "Username")
        self.signup_username = ModernLineEdit("Choose a username")
        self.signup_username.setStyleSheet(self._get_lineedit_style())
        card_layout.addWidget(self.signup_username)

        # Email
        self._add_field_label(card_layout, "Email")
        self.signup_email = ModernLineEdit("Enter your email")
        self.signup_email.setStyleSheet(self._get_lineedit_style())
        card_layout.addWidget(self.signup_email)

        # Password
        self._add_field_label(card_layout, "Password")
        self.signup_password = ModernLineEdit("Create a password")
        self.signup_password.setEchoMode(QLineEdit.Password)
        self.signup_password.setStyleSheet(self._get_lineedit_style())
        card_layout.addWidget(self.signup_password)

        # Confirm Password
        self._add_field_label(card_layout, "Confirm Password")
        self.signup_confirm = ModernLineEdit("Re-enter password")
        self.signup_confirm.setEchoMode(QLineEdit.Password)
        self.signup_confirm.setStyleSheet(self._get_lineedit_style())
        card_layout.addWidget(self.signup_confirm)

        # Error label
        self.signup_error = ErrorLabel()
        card_layout.addWidget(self.signup_error)

        card_layout.addSpacing(8)

        # Signup button
        self.signup_button = ModernButton("Create Account")
        card_layout.addWidget(self.signup_button)

        # Cancel link
        cancel_layout = QHBoxLayout()
        cancel_layout.setContentsMargins(0, 0, 0, 0)
        cancel_layout.setSpacing(4)

        have_account = QLabel("Already have an account?")
        have_account.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; border: none;")
        cancel_layout.addWidget(have_account)

        self.cancel_link = QPushButton("Sign in")
        self.cancel_link.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_GREEN_SECONDARY};
                border: none;
                text-decoration: underline;
                font-weight: bold;
                font-size: 10px;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLOR_GREEN_LIGHT};
            }}
        """)
        self.cancel_link.setCursor(Qt.PointingHandCursor)
        cancel_layout.addWidget(self.cancel_link)

        cancel_container = QWidget()
        cancel_container.setStyleSheet("border: none;")
        cancel_container.setLayout(cancel_layout)
        card_layout.addWidget(cancel_container, alignment=Qt.AlignCenter)

        # Close button (X)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_SECONDARY};
                border: none;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)
        close_btn.setCursor(Qt.PointingHandCursor)

        # Position close button via overlay
        btn_container = QWidget()
        btn_container.setStyleSheet("border: none;")
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        main_layout.addWidget(btn_container)
        main_layout.addWidget(card)
        main_layout.addStretch()

        self.close_btn = close_btn

    def _add_field_label(self, layout: QVBoxLayout, text: str):
        """Add a field label to the layout."""
        label = QLabel(text)
        label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; border: none;")
        label.setFont(QFont(APP_FONT, 10))
        layout.addWidget(label)

    def _get_lineedit_style(self) -> str:
        """Get stylesheet for line edit inputs."""
        return f"""
            QLineEdit {{
                background-color: #1a1a2e;
                border: 2px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 12px 15px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 11px;
                font-family: '{APP_FONT}';
                selection-background-color: {COLOR_GREEN_SECONDARY};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_GREEN_SECONDARY};
                background-color: {COLOR_DARK_HOVER};
            }}
            QLineEdit::placeholder {{
                color: {COLOR_TEXT_MUTED};
            }}
        """

    def _connect_signals(self):
        """Connect dialog signals."""
        self.close_btn.clicked.connect(self.reject)
        self.cancel_link.clicked.connect(self.reject)
        self.signup_button.clicked.connect(self._on_signup_clicked)

        # Enter key support
        self.signup_confirm.returnPressed.connect(self._on_signup_clicked)

    def _validate_inputs(self) -> Optional[str]:
        """Validate all inputs. Returns error message or None."""
        username = self.signup_username.text().strip()
        email = self.signup_email.text().strip()
        password = self.signup_password.text()
        confirm = self.signup_confirm.text()

        if not username:
            return "Please enter a username."
        if len(username) < 3:
            return "Username must be at least 3 characters."
        if not email:
            return "Please enter an email address."
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return "Please enter a valid email address."
        if not password:
            return "Please enter a password."
        if len(password) < 6:
            return "Password must be at least 6 characters."
        if password != confirm:
            return "Passwords do not match."
        return None

    def _set_inputs_enabled(self, enabled: bool):
        """Enable or disable input fields."""
        self.signup_username.setEnabled(enabled)
        self.signup_email.setEnabled(enabled)
        self.signup_password.setEnabled(enabled)
        self.signup_confirm.setEnabled(enabled)
        self.cancel_link.setEnabled(enabled)
        self.close_btn.setEnabled(enabled)

    def _on_signup_clicked(self):
        """Handle signup button click."""
        # Validate
        error = self._validate_inputs()
        if error:
            self.signup_error.show_error(error)
            return

        self.signup_error.hide_error()

        # Loading state
        self.signup_button.set_loading(True)
        self._set_inputs_enabled(False)

        # Run signup in background
        username = self.signup_username.text().strip()
        email = self.signup_email.text().strip()
        password = self.signup_password.text()

        self._thread = QThread()
        self._worker = SignupWorker("localhost", 8080, username, email, password)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.signup_success.connect(self._on_signup_success)
        self._worker.signup_failed.connect(self._on_signup_failed)
        self._worker.signup_success.connect(self._thread.quit)
        self._worker.signup_failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_signup_success(self, data: Dict[str, Any]):
        """Handle successful signup."""
        self.signup_button.set_loading(False)
        self._set_inputs_enabled(True)
        print(f"Signup successful for user: {data.get('username')}")
        self.accept()

    def _on_signup_failed(self, message: str):
        """Handle signup failure."""
        self.signup_button.set_loading(False)
        self._set_inputs_enabled(True)
        self.signup_error.show_error(message)


# ────────────────────────────────────────────────────────────
# LoginCard — login form with real backend integration
# ────────────────────────────────────────────────────────────

class LoginCard(QFrame):
    """Login form card with modern styling and real backend integration"""

    # Signals for communicating with parent
    login_started = Signal()
    login_success = Signal(dict)
    login_failed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self._login_thread: Optional[QThread] = None
        self._login_worker: Optional[LoginWorker] = None

        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)

        # Title
        title = QLabel("LAN Secure File System")
        title_font = QFont(APP_FONT, 26, QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Enterprise-Grade File Security")
        subtitle_font = QFont(APP_FONT, 11)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(24)

        # Username input
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold;")
        username_font = QFont(APP_FONT, 10)
        username_label.setFont(username_font)
        layout.addWidget(username_label)

        self.username_input = ModernLineEdit("Enter your username")
        self.username_input.setStyleSheet(self._get_lineedit_style())
        layout.addWidget(self.username_input)

        # Password input
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold;")
        password_label.setFont(username_font)
        layout.addWidget(password_label)

        self.password_input = ModernLineEdit("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(self._get_lineedit_style())
        layout.addWidget(self.password_input)

        # Remember me checkbox
        self.remember_checkbox = QCheckBox("Remember me")
        self.remember_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {COLOR_TEXT_SECONDARY};
                font-size: 10px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {COLOR_DARK_CARD};
                border: 2px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_GREEN_SECONDARY};
                border: 2px solid {COLOR_GREEN_SECONDARY};
                border-radius: 4px;
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLOR_GREEN_LIGHT};
            }}
        """)
        layout.addWidget(self.remember_checkbox)

        # Error label for login
        self.login_error = ErrorLabel()
        layout.addWidget(self.login_error)

        layout.addSpacing(6)

        # Login button
        self.login_button = ModernButton("Sign In")
        layout.addWidget(self.login_button)

        # Signup text
        signup_layout = QHBoxLayout()
        signup_layout.setContentsMargins(0, 0, 0, 0)

        signup_text = QLabel("Don't have an account? ")
        signup_text.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px;")
        signup_layout.addWidget(signup_text)

        self.signup_link = QPushButton("Sign up")
        self.signup_link.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_GREEN_SECONDARY};
                border: none;
                text-decoration: underline;
                font-weight: bold;
                font-size: 10px;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLOR_GREEN_LIGHT};
            }}
        """)
        self.signup_link.setCursor(Qt.PointingHandCursor)
        signup_layout.addWidget(self.signup_link)

        signup_container = QWidget()
        signup_container.setLayout(signup_layout)
        layout.addWidget(signup_container, alignment=Qt.AlignCenter)

        # Server status indicator
        layout.addSpacing(12)
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #555555; font-size: 14px;")
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("Checking server...")
        self.status_text.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9px;")
        status_layout.addWidget(self.status_text)

        status_layout.addStretch()
        status_container = QWidget()
        status_container.setLayout(status_layout)
        layout.addWidget(status_container)

        layout.addStretch()

    @staticmethod
    def _get_lineedit_style() -> str:
        """Get stylesheet for line edit inputs with focus glow."""
        return f"""
            QLineEdit {{
                background-color: {COLOR_DARK_CARD};
                border: 2px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 12px 15px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 11px;
                font-family: '{APP_FONT}';
                selection-background-color: {COLOR_GREEN_SECONDARY};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_GREEN_SECONDARY};
                background-color: {COLOR_DARK_HOVER};
            }}
            QLineEdit::placeholder {{
                color: {COLOR_TEXT_MUTED};
            }}
        """

    def set_server_status(self, online: bool):
        """Update the server status indicator."""
        if online:
            self.status_indicator.setStyleSheet(f"color: {COLOR_GREEN_SECONDARY}; font-size: 14px;")
            self.status_text.setText("Coordinator Server Online")
            self.status_text.setStyleSheet(f"color: {COLOR_GREEN_LIGHT}; font-size: 9px; font-weight: bold;")
        else:
            self.status_indicator.setStyleSheet(f"color: {COLOR_RED}; font-size: 14px;")
            self.status_text.setText("Coordinator Server Offline")
            self.status_text.setStyleSheet(f"color: {COLOR_ERROR_TEXT}; font-size: 9px;")

    def set_login_loading(self, loading: bool):
        """Set login loading state."""
        self.login_button.set_loading(loading)
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.remember_checkbox.setEnabled(not loading)
        self.signup_link.setEnabled(not loading)

    def show_login_error(self, message: str):
        """Show login error inline."""
        self.login_error.show_error(message)

    def hide_login_error(self):
        """Hide login error."""
        self.login_error.hide_error()

    def get_credentials(self) -> tuple:
        """Get username and password from inputs."""
        return self.username_input.text().strip(), self.password_input.text()


# ────────────────────────────────────────────────────────────
# LoginWindow — main window
# ────────────────────────────────────────────────────────────

class LoginWindow(QMainWindow):
    """Main login window combining decorative panel and login form"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LAN Secure File System - Login")
        self.setGeometry(100, 100, 1200, 700)
        self.setMinimumSize(QSize(1000, 600))

        # Backend integration
        self._backend_service: Optional[BackendService] = None

        # Threading
        self._status_thread: Optional[QThread] = None
        self._status_worker: Optional[ServerStatusWorker] = None

        # Fade-in opacity
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(400)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # Setup central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left decorative panel
        self.decorative_panel = DecorativePanel()
        main_layout.addWidget(self.decorative_panel)

        # Right login card
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignCenter)

        self.login_card = LoginCard()
        right_layout.addWidget(self.login_card, alignment=Qt.AlignCenter)

        main_layout.addWidget(right_widget, 1)

        # Set application-wide dark theme
        self._apply_dark_theme(central_widget)

        # Connect signals
        self._connect_signals()

        # Start fade-in after window is shown
        QTimer.singleShot(50, self._fade_in.start)

        # Start server status checking
        QTimer.singleShot(100, self._start_status_checking)

    def showEvent(self, event):
        """Ensure window is properly shown before fade-in."""
        super().showEvent(event)

    def _apply_dark_theme(self, widget: QWidget):
        """Apply dark theme to application"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(COLOR_DARK_BG))
        palette.setColor(QPalette.WindowText, QColor(COLOR_TEXT_PRIMARY))
        palette.setColor(QPalette.Base, QColor(COLOR_DARK_CARD))
        palette.setColor(QPalette.Text, QColor(COLOR_TEXT_PRIMARY))
        palette.setColor(QPalette.Button, QColor("#0a0e27"))
        palette.setColor(QPalette.ButtonText, QColor(COLOR_TEXT_PRIMARY))

        widget.setPalette(palette)

    # ── Server Status Checking ──

    def _start_status_checking(self):
        """Start the server status background worker thread."""
        self._status_thread = QThread()
        self._status_worker = ServerStatusWorker(host="localhost", port=8080)
        self._status_worker.moveToThread(self._status_thread)
        self._status_thread.started.connect(self._status_worker.run)
        self._status_worker.status_changed.connect(self._on_server_status_changed)
        self._status_thread.finished.connect(self._status_worker.deleteLater)
        self._status_thread.start()

    def _stop_status_checking(self):
        """Stop the server status worker thread."""
        if self._status_worker:
            self._status_worker.stop()
        if self._status_thread and self._status_thread.isRunning():
            self._status_thread.quit()
            self._status_thread.wait(3000)

    def _on_server_status_changed(self, online: bool):
        """Handle server status change from background worker."""
        self.login_card.set_server_status(online)

    # ── Signal Connections ──

    def _connect_signals(self):
        """Connect button signals to slots."""
        # Login button
        self.login_card.login_button.clicked.connect(self._on_login_clicked)

        # Enter key in password field triggers login
        self.login_card.password_input.returnPressed.connect(self._on_login_clicked)

        # Enter key in username field moves to password
        self.login_card.username_input.returnPressed.connect(
            lambda: self.login_card.password_input.setFocus()
        )

        # Signup link
        self.login_card.signup_link.clicked.connect(self._on_signup_clicked)

        # Login card signals
        self.login_card.login_success.connect(self._on_login_success)
        self.login_card.login_failed.connect(self._on_login_failed)

    # ── Login Flow ──

    def _on_login_clicked(self):
        """Handle login button click with real backend integration."""
        username, password = self.login_card.get_credentials()

        # Validate inputs
        if not username:
            self.login_card.show_login_error("Please enter your username.")
            self.login_card.username_input.setFocus()
            return
        if not password:
            self.login_card.show_login_error("Please enter your password.")
            self.login_card.password_input.setFocus()
            return

        # Clear previous errors
        self.login_card.hide_login_error()

        # Show loading state
        self.login_card.set_login_loading(True)

        # Run login in background thread
        self._login_thread = QThread()
        self._login_worker = LoginWorker(
            "localhost", 8080,
            username, password
        )
        self._login_worker.moveToThread(self._login_thread)
        self._login_thread.started.connect(self._login_worker.run)
        self._login_worker.login_success.connect(self._on_login_success)
        self._login_worker.login_failed.connect(self._on_login_failed)
        self._login_worker.login_success.connect(self._login_thread.quit)
        self._login_worker.login_failed.connect(self._login_thread.quit)
        self._login_thread.finished.connect(self._login_thread.deleteLater)
        self._login_thread.finished.connect(self._login_worker.deleteLater)
        self._login_thread.start()

    def _on_login_success(self, data: Dict[str, Any]):
        """Handle successful login."""
        self.login_card.set_login_loading(False)
        username = data.get("username", "Unknown")
        print(f"Login successful for user: {username}")
        print(f"Remember me: {self.login_card.remember_checkbox.isChecked()}")

        # Placeholder for future MainWindow transition
        self._prepare_transition()

    def _on_login_failed(self, message: str):
        """Handle login failure."""
        self.login_card.set_login_loading(False)
        self.login_card.show_login_error(message)

    def _prepare_transition(self):
        """
        Prepare transition placeholder for future MainWindow.
        Currently prints success and keeps window open for testing.
        """
        # In the future, this will hide login and show MainWindow
        pass

    # ── Signup Flow ──

    def _on_signup_clicked(self):
        """Open the signup dialog."""
        dialog = SignupDialog(self)
        result = dialog.exec()

        if result == QDialog.Accepted:
            print("Signup dialog accepted — user registered successfully.")
        else:
            print("Signup dialog cancelled.")

    # ── Cleanup ──

    def closeEvent(self, event):
        """Clean up threads when window closes."""
        self._stop_status_checking()
        super().closeEvent(event)


# ────────────────────────────────────────────────────────────
# Entry Point
# ────────────────────────────────────────────────────────────

def main():
    """Entry point for the application"""
    app = QApplication(sys.argv)

    # Set application-wide font
    font = QFont(APP_FONT, 10)
    app.setFont(font)

    # Create and show login window
    login_window = LoginWindow()
    login_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()