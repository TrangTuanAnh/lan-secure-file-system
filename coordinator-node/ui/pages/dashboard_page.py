"""Dashboard window using reusable enterprise widgets and backend services."""

from __future__ import annotations

import sys
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
    QBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import APP_CONFIG
from network.backend_client_sdk import BackendConfig
from services.services import BackendService
from ui.fonts import app_font, load_app_fonts, ui_font, ui_font_family
from ui.pages.login_page import LoginRuntimeConfig
from ui.widgets.activity_item import ActivityItem
from ui.widgets.app_shell import AppShell
from ui.widgets.dashboard_stat_card import DashboardStatCard
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.room_card import RoomCard
from ui.widgets.status_badge import StatusBadge
from ui.widgets.top_bar import TopBar


@dataclass(frozen=True)
class DashboardRuntimeConfig:
    """Backend runtime settings for the dashboard."""

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


class DashboardDataWorker(QObject):
    """Loads dashboard data off the GUI thread."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, config: BackendConfig, token: str = "", username: str = "") -> None:
        super().__init__()
        self._config = config
        self._token = token
        self._username = username

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._config)
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return

            if self._token:
                service._client.set_token(self._token)

            status_payload: Dict[str, Any] = {}
            server_online = service.health_check()
            try:
                status_payload = service._client.status()
            except Exception:
                status_payload = {}

            rooms = []
            if self._token:
                rooms = service.rooms.get_rooms()

            normalized_rooms: list[dict[str, Any]] = []
            total_files = 0
            for room in rooms:
                room_id = room.get("roomId") or room.get("id") or ""
                room_name = room.get("name") or room.get("roomName") or "Untitled Room"
                role = (
                    room.get("role")
                    or room.get("memberRole")
                    or room.get("myRole")
                    or room.get("permission")
                    or "Member"
                )
                member_count = room.get("memberCount") or room.get("membersCount") or 0
                file_count = room.get("fileCount")
                if file_count is None and room_id:
                    try:
                        files = service.files.get_files(room_id)
                        file_count = len(files)
                    except Exception:
                        file_count = 0
                file_count = file_count or 0
                total_files += int(file_count)
                normalized_rooms.append(
                    {
                        "room_id": room_id,
                        "room_name": room_name,
                        "role": role,
                        "member_count": int(member_count or 0),
                        "file_count": int(file_count),
                        "summary": room.get("description")
                        or room.get("summary")
                        or "Secure collaborative room with encrypted document access.",
                    }
                )

            stats = {
                "room_count": len(normalized_rooms),
                "file_count": total_files,
                "member_count": sum(room["member_count"] for room in normalized_rooms),
                "server_label": status_payload.get("status") or ("Online" if server_online else "Offline"),
            }

            payload = {
                "server_online": server_online,
                "server_message": "Coordinator Server Online" if server_online else "Coordinator Server Offline",
                "server_status": status_payload,
                "user": {
                    "username": self._username or "Authenticated User",
                    "email": "",
                    "role": "Secure Operator",
                    "token_present": bool(self._token),
                },
                "rooms": normalized_rooms,
                "activities": [],
                "stats": stats,
            }
            self.success.emit(payload)
        except TimeoutError:
            self.failure.emit("Dashboard data request timed out. Please try again.")
        except Exception as exc:
            self.failure.emit(f"Failed to load dashboard data: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class DashboardWindow(QMainWindow):
    """Main dashboard window after authentication."""

    room_open_requested = Signal(str)
    logout_requested = Signal()

    def __init__(
        self,
        username: str = "",
        token: str = "",
        runtime: Optional[DashboardRuntimeConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime or DashboardRuntimeConfig()
        self._username = username
        self._token = token
        self._backend_service = BackendService(self._runtime.to_backend_config())
        self._data_thread: Optional[QThread] = None
        self._data_worker: Optional[DashboardDataWorker] = None
        self._room_cards: list[RoomCard] = []
        self._activity_widgets: list[QWidget] = []
        self._stat_cards: list[DashboardStatCard] = []

        self.setWindowTitle("LAN Secure File System - Dashboard")
        self.setMinimumSize(QSize(1260, 760))
        self.resize(1360, 840)

        self._build_ui()
        self._apply_window_theme()
        self._connect_signals()
        self._setup_fade_in()

        QTimer.singleShot(50, self._fade_in.start)
        QTimer.singleShot(120, self._load_dashboard_data)

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("dashboardCentralWidget")
        self.setCentralWidget(central_widget)

        root = QVBoxLayout(central_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.app_shell = AppShell()
        root.addWidget(self.app_shell)

        self.error_toast = ErrorLabel(parent=self)
        self.error_toast.move_to_top_center(self)

        self.app_shell.sidebar_nav.add_nav_item("overview", "Overview", checked=True)
        self.app_shell.sidebar_nav.add_nav_item("rooms", "My Rooms")
        self.app_shell.sidebar_nav.add_nav_item("activity", "Recent Activity")
        self.app_shell.sidebar_nav.add_nav_item("settings", "Security Settings")
        self.app_shell.sidebar_nav.set_user_info(self._username or "Authenticated User", "Session Active", "Secure Operator")

        self.top_bar = TopBar(
            page_title="Security Overview",
            subtitle="Loading workspace telemetry and room intelligence...",
            user_display=self._username or "Authenticated User",
        )
        self.top_bar.set_server_status("Loading", "warning")
        self.app_shell.add_content_widget(self.top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("dashboardScrollArea")

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("dashboardScrollContent")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 12)
        self.scroll_layout.setSpacing(18)
        self.scroll_area.setWidget(self.scroll_content)
        self.app_shell.add_content_widget(self.scroll_area, 1)

        self.stats_grid = QGridLayout()
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setHorizontalSpacing(16)
        self.stats_grid.setVerticalSpacing(16)
        self.scroll_layout.addLayout(self.stats_grid)

        self.rooms_section = self._build_section_frame("My Rooms", "Rooms available to your authenticated session.")
        self.rooms_content = QVBoxLayout()
        self.rooms_content.setContentsMargins(0, 0, 0, 0)
        self.rooms_content.setSpacing(14)
        self.rooms_section["body"].addLayout(self.rooms_content)
        self.scroll_layout.addWidget(self.rooms_section["frame"])

        lower_row = QBoxLayout(QBoxLayout.LeftToRight)
        lower_row.setContentsMargins(0, 0, 0, 0)
        lower_row.setSpacing(16)
        self.lower_row = lower_row
        self.scroll_layout.addLayout(lower_row)

        self.activity_section = self._build_section_frame("Recent Activity", "Realtime activity stream from monitored rooms.")
        self.activity_content = QVBoxLayout()
        self.activity_content.setContentsMargins(0, 0, 0, 0)
        self.activity_content.setSpacing(12)
        self.activity_section["body"].addLayout(self.activity_content)
        lower_row.addWidget(self.activity_section["frame"], 2)

        self.quick_actions_section = self._build_section_frame("Quick Actions", "Fast access to the next operations step.")
        self.quick_actions_content = QVBoxLayout()
        self.quick_actions_content.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_content.setSpacing(12)
        self.quick_actions_section["body"].addLayout(self.quick_actions_content)
        lower_row.addWidget(self.quick_actions_section["frame"], 1)

        self._build_stat_cards()
        self._build_quick_actions()
        self._set_loading_state(True)
        self._relayout_dashboard_sections()

    def _build_section_frame(self, title: str, subtitle: str) -> dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("dashboardSection")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setFont(app_font(14, 700))
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("sectionSubtitle")
        subtitle_label.setFont(ui_font(9))
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        body = QVBoxLayout()
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(14)
        layout.addLayout(body)
        return {"frame": frame, "body": body}

    def _build_stat_cards(self) -> None:
        self.rooms_stat = DashboardStatCard("Rooms", "--", "Accessible encrypted rooms", "RM", PALETTE.accent_alt)
        self.files_stat = DashboardStatCard("Files", "--", "Protected assets indexed", "FL", PALETTE.accent_soft)
        self.members_stat = DashboardStatCard("Members", "--", "Collaborators across rooms", "MB", "#72d6ff")
        self.status_stat = DashboardStatCard("Server", "Loading", "Coordinator availability", "SV", PALETTE.accent_bright)

        self._stat_cards = [self.rooms_stat, self.files_stat, self.members_stat, self.status_stat]
        self._rebuild_stats_grid()

    def _build_quick_actions(self) -> None:
        self.refresh_button = ModernButton("Refresh Dashboard")
        self.refresh_button.clicked.connect(self._load_dashboard_data)
        self.quick_actions_content.addWidget(self.refresh_button)

        self.create_room_button = ModernButton("Create Secure Room")
        self.create_room_button.set_accent_color(PALETTE.accent_soft)
        self.create_room_button.clicked.connect(lambda: print("Quick action selected: create_room"))
        self.quick_actions_content.addWidget(self.create_room_button)

        self.manage_access_button = ModernButton("Review Access")
        self.manage_access_button.set_accent_color("#72d6ff")
        self.manage_access_button.clicked.connect(lambda: print("Quick action selected: review_access"))
        self.quick_actions_content.addWidget(self.manage_access_button)

        self.quick_status_badge = StatusBadge("SESSION ACTIVE", "online")
        self.quick_actions_content.addWidget(self.quick_status_badge, 0, Qt.AlignLeft)

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
            QWidget#dashboardCentralWidget,
            QWidget#dashboardScrollContent {{
                background-color: {PALETTE.background};
            }}
            QScrollArea#dashboardScrollArea {{
                background: transparent;
                border: none;
            }}
            QFrame#dashboardSection {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 24px;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#sectionTitle {{
                color: #f4fff9;
            }}
            QLabel#sectionSubtitle {{
                color: #8aa39a;
            }}
            """
        )

    def _connect_signals(self) -> None:
        self.app_shell.sidebar_nav.navigation_requested.connect(self._on_navigation_requested)
        self.app_shell.sidebar_nav.logout_requested.connect(self._on_logout_requested)
        self.top_bar.search_changed.connect(self._filter_rooms)

    def _setup_fade_in(self) -> None:
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_in.setDuration(420)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_toast.move_to_top_center(self)
        self._relayout_dashboard_sections()

    def _rebuild_stats_grid(self) -> None:
        while self.stats_grid.count():
            item = self.stats_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.scroll_content)

        available_width = max(0, self.scroll_area.viewport().width())
        if available_width >= 980:
            columns = 4
        elif available_width >= 620:
            columns = 2
        else:
            columns = 1

        for index, card in enumerate(self._stat_cards):
            row = index // columns
            column = index % columns
            self.stats_grid.addWidget(card, row, column)

        for column in range(columns):
            self.stats_grid.setColumnStretch(column, 1)

    def _relayout_dashboard_sections(self) -> None:
        self._rebuild_stats_grid()
        available_width = max(0, self.scroll_area.viewport().width())
        if available_width and available_width < 920:
            self.lower_row.setDirection(QBoxLayout.TopToBottom)
        else:
            self.lower_row.setDirection(QBoxLayout.LeftToRight)

    def _load_dashboard_data(self) -> None:
        if self._data_thread and self._data_thread.isRunning():
            return

        self._set_loading_state(True)
        self.error_toast.hide_error()
        self.top_bar.set_subtitle("Loading workspace telemetry and room intelligence...")
        self.top_bar.set_server_status("Loading", "warning")

        self._data_thread = QThread(self)
        self._data_worker = DashboardDataWorker(
            self._runtime.to_backend_config(),
            token=self._token,
            username=self._username,
        )
        self._data_worker.moveToThread(self._data_thread)
        self._data_thread.started.connect(self._data_worker.run)
        self._data_worker.success.connect(self._on_dashboard_data_loaded)
        self._data_worker.failure.connect(self._on_dashboard_data_failed)
        self._data_worker.success.connect(self._data_thread.quit)
        self._data_worker.failure.connect(self._data_thread.quit)
        self._data_thread.finished.connect(self._data_thread.deleteLater)
        self._data_thread.finished.connect(self._data_worker.deleteLater)
        self._data_thread.start()

    def _set_loading_state(self, loading: bool) -> None:
        for button in (self.refresh_button, self.create_room_button, self.manage_access_button):
            button.set_loading(loading, "Loading" if loading else None)
            if not loading:
                button.set_loading(False)
        self.top_bar.search_input.setEnabled(not loading)
        self.app_shell.sidebar_nav.logout_button.setEnabled(not loading)

    def _on_dashboard_data_loaded(self, payload: Dict[str, Any]) -> None:
        self._set_loading_state(False)

        user_info = payload.get("user", {})
        username = user_info.get("username") or self._username or "Authenticated User"
        self.top_bar.set_user_display(username)
        self.app_shell.sidebar_nav.set_user_info(
            username,
            user_info.get("email") or "Session Active",
            user_info.get("role") or "Secure Operator",
        )

        server_online = payload.get("server_online", False)
        self.top_bar.set_server_status("Online" if server_online else "Offline", "online" if server_online else "offline")
        self.top_bar.set_subtitle(payload.get("server_message", "Dashboard ready."))
        self.quick_status_badge.set_variant("online" if user_info.get("token_present") else "warning")
        self.quick_status_badge.setText("SESSION ACTIVE" if user_info.get("token_present") else "LIMITED SESSION")

        stats = payload.get("stats", {})
        self.rooms_stat.set_value(str(stats.get("room_count", 0)))
        self.files_stat.set_value(str(stats.get("file_count", 0)))
        self.members_stat.set_value(str(stats.get("member_count", 0)))
        self.status_stat.set_value(stats.get("server_label", "Unknown"))
        self.status_stat.set_subtitle("Coordinator backend health and transport status.")

        self._render_rooms(payload.get("rooms", []))
        self._render_activities(payload.get("activities", []))

    def _on_dashboard_data_failed(self, message: str) -> None:
        self._set_loading_state(False)
        self.top_bar.set_server_status("Offline", "offline")
        self.top_bar.set_subtitle("Unable to load secure workspace data.")
        self.error_toast.move_to_top_center(self)
        self.error_toast.show_error(message)
        self._render_rooms([])
        self._render_activities([])

    def _render_rooms(self, rooms: list[dict[str, Any]]) -> None:
        while self.rooms_content.count():
            item = self.rooms_content.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._room_cards.clear()

        if not rooms:
            self.rooms_content.addWidget(self._build_empty_state("No rooms available yet."))
            return

        for room in rooms:
            card = RoomCard(
                room_id=room.get("room_id", ""),
                room_name=room.get("room_name", "Untitled Room"),
                role=room.get("role", "Member"),
                file_count=room.get("file_count", 0),
                member_count=room.get("member_count", 0),
            )
            card.set_summary(room.get("summary", "Secure collaborative room with encrypted document access."))
            card.open_requested.connect(self._on_room_open_requested)
            self.rooms_content.addWidget(card)
            self._room_cards.append(card)

    def _render_activities(self, activities: list[dict[str, Any]]) -> None:
        while self.activity_content.count():
            item = self.activity_content.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._activity_widgets.clear()

        if not activities:
            self.activity_content.addWidget(self._build_empty_state("No recent activity yet."))
            return

        for activity in activities:
            item = ActivityItem(
                activity_type=activity.get("type", "Activity"),
                message=activity.get("message", ""),
                timestamp=activity.get("timestamp", ""),
            )
            self.activity_content.addWidget(item)
            self._activity_widgets.append(item)

    def _build_empty_state(self, message: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dashboardEmptyState")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setFont(ui_font(10))
        label.setStyleSheet("color: #8aa39a;")
        layout.addWidget(label)
        frame.setStyleSheet(
            """
            QFrame#dashboardEmptyState {
                background-color: rgba(15, 15, 30, 150);
                border: 1px dashed rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
            """
        )
        return frame

    def _filter_rooms(self, query: str) -> None:
        normalized = query.strip().lower()
        for card in self._room_cards:
            room_name = card.room_name_label.text().lower()
            summary = card.summary_label.text().lower()
            matches = not normalized or normalized in room_name or normalized in summary
            card.setVisible(matches)

    def _on_navigation_requested(self, item_id: str) -> None:
        print(f"Navigation requested: {item_id}")

    def _on_room_open_requested(self, room_id: str) -> None:
        print(f"Open room requested: {room_id}")
        self.room_open_requested.emit(room_id)

    def _on_logout_requested(self) -> None:
        self.logout_requested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._data_thread and self._data_thread.isRunning():
            self._data_thread.quit()
            self._data_thread.wait(2000)
        if self._backend_service.is_connected():
            self._backend_service.disconnect()
        super().closeEvent(event)


def main() -> None:
    """Run the dashboard as a standalone desktop entry point."""
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    dashboard = DashboardWindow(
        username="Secure Operator",
        token="",
        runtime=DashboardRuntimeConfig(),
    )
    dashboard.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
