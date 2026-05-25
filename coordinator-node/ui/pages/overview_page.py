"""Overview content page for the authenticated dashboard."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from services.services import BackendService
from ui.dashboard_runtime import DashboardRuntimeConfig
from ui.fonts import app_font, ui_font, ui_font_family
from ui.recent_rooms import RecentRoomsStore
from ui.widgets.activity_item import ActivityItem
from ui.widgets.dashboard_stat_card import DashboardStatCard
from ui.widgets.empty_state import EmptyState
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE
from ui.widgets.top_bar import TopBar
from ui.widgets.room_card import RoomCard


class OverviewDataWorker(QObject):
    """Loads overview data without blocking the GUI thread."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str = "", username: str = "", global_role: str = "") -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._username = username
        self._global_role = global_role

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return

            if self._token:
                service._client.set_token(self._token)

            server_online = service.health_check()
            try:
                status_payload = service._client.status()
            except Exception:
                status_payload = {}

            rooms = service.rooms.get_rooms() if self._token else []
            normalized_rooms: list[dict[str, Any]] = []
            total_files = 0
            total_members = 0

            for room in rooms:
                room_id = room.get("roomId") or room.get("id") or ""
                room_name = room.get("name") or room.get("roomName") or "Untitled Room"
                role = room.get("role") or room.get("memberRole") or room.get("myRole")
                member_count = int(room.get("memberCount") or room.get("membersCount") or 0)
                file_count = room.get("fileCount")
                if file_count is None and room_id:
                    try:
                        file_count = len(service.files.get_files(room_id))
                    except Exception:
                        file_count = 0

                normalized_rooms.append(
                    {
                        "room_id": room_id,
                        "room_name": room_name,
                        "role": role,
                        "member_count": member_count,
                        "file_count": int(file_count or 0),
                        "summary": room.get("description")
                        or room.get("summary")
                        or "Secure collaborative room with encrypted document access.",
                        "last_activity": room.get("lastActivity") or room.get("updatedAt") or "No recent activity recorded.",
                    }
                )
                total_files += int(file_count or 0)
                total_members += member_count

            payload = {
                "server_online": server_online,
                "server_message": "Coordinator Server Online" if server_online else "Coordinator Server Offline",
                "server_status": status_payload,
                "user": {
                    "username": self._username or "Authenticated User",
                    "email": "",
                    "global_role": self._global_role or "USER",
                    "token_present": bool(self._token),
                },
                "rooms": normalized_rooms,
                "activities": [],
                "stats": {
                    "room_count": len(normalized_rooms),
                    "file_count": total_files,
                    "member_count": total_members,
                    "server_label": status_payload.get("status") or ("Online" if server_online else "Offline"),
                },
            }
            self.success.emit(payload)
        except TimeoutError:
            self.failure.emit("Overview request timed out. Please try again.")
        except Exception as exc:
            self.failure.emit(f"Failed to load overview data: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class OverviewPage(QWidget):
    """Dashboard overview content displayed inside the shared shell."""

    room_open_requested = Signal(dict)
    rooms_loaded = Signal(list)

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
        self._runtime = runtime or DashboardRuntimeConfig()
        self._username = username
        self._user_id = user_id
        self._email = email
        self._token = token
        self._global_role = global_role
        self._data_thread: Optional[QThread] = None
        self._data_worker: Optional[OverviewDataWorker] = None
        self._room_cards: list[RoomCard] = []
        self._activity_widgets: list[QWidget] = []
        self._stat_cards: list[DashboardStatCard] = []
        self._remote_activities: list[dict[str, Any]] = []
        self._local_activities: list[dict[str, Any]] = []
        self._recent_rooms: list[dict[str, Any]] = RecentRoomsStore.load()

        self._build_ui()
        self._apply_styles()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        self.error_toast = ErrorLabel(parent=self)
        self.error_toast.move_to_top_center(self)

        self.top_bar = TopBar(
            page_title="Overview",
            subtitle="Loading workspace telemetry and room intelligence...",
            user_display=self._username or "Authenticated User",
            show_refresh_button=True,
        )
        self.top_bar.set_server_status("Loading", "warning")
        self.top_bar.set_user_role(self._display_global_role())
        self.top_bar.refresh_requested.connect(self.reload)
        root.addWidget(self.top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("overviewScrollArea")
        root.addWidget(self.scroll_area, 1)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("overviewScrollContent")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 12)
        self.scroll_layout.setSpacing(18)
        self.scroll_area.setWidget(self.scroll_content)

        self.stats_grid = QGridLayout()
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setHorizontalSpacing(16)
        self.stats_grid.setVerticalSpacing(16)
        self.scroll_layout.addLayout(self.stats_grid)

        self.rooms_section = self._build_section_frame("Recent Rooms", "Quick access to recently opened rooms.")
        self.rooms_content = QVBoxLayout()
        self.rooms_content.setContentsMargins(0, 0, 0, 0)
        self.rooms_content.setSpacing(14)
        self.rooms_section["body"].addLayout(self.rooms_content)
        self.scroll_layout.addWidget(self.rooms_section["frame"])

        self.activity_section = self._build_section_frame("Recent Activity", "Realtime activity stream from monitored rooms.")
        self.activity_content = QVBoxLayout()
        self.activity_content.setContentsMargins(0, 0, 0, 0)
        self.activity_content.setSpacing(10)
        self.activity_section["body"].addLayout(self.activity_content)
        self.scroll_layout.addWidget(self.activity_section["frame"])

        self._build_stat_cards()
        self._set_loading_state(True)

    def _build_section_frame(self, title: str, subtitle: str) -> dict[str, Any]:
        from PySide6.QtWidgets import QLabel

        frame = QFrame()
        frame.setObjectName("overviewSection")
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

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget#overviewScrollContent {{
                background-color: transparent;
            }}
            QScrollArea#overviewScrollArea {{
                background: transparent;
                border: none;
            }}
            QFrame#overviewSection {{
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_toast.move_to_top_center(self)
        self._rebuild_stats_grid()

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

    def _set_loading_state(self, loading: bool) -> None:
        self.top_bar.set_refresh_enabled(not loading)
        self.top_bar.search_input.setEnabled(not loading)

    def _display_global_role(self) -> str:
        return "Administrator" if self._global_role.upper() == "ADMIN" else "Secure Operator"

    def reload(self) -> None:
        if self._data_thread and self._data_thread.isRunning():
            return

        self._set_loading_state(True)
        self.error_toast.hide_error()
        self.top_bar.set_subtitle("Loading workspace telemetry and room intelligence...")
        self.top_bar.set_server_status("Loading", "warning")

        self._data_thread = QThread(self)
        self._data_worker = OverviewDataWorker(
            self._runtime,
            token=self._token,
            username=self._username,
            global_role=self._global_role,
        )
        self._data_worker.moveToThread(self._data_thread)
        self._data_thread.started.connect(self._data_worker.run)
        self._data_worker.success.connect(self._on_data_loaded)
        self._data_worker.failure.connect(self._on_data_failed)
        self._data_worker.success.connect(self._data_thread.quit)
        self._data_worker.failure.connect(self._data_thread.quit)
        self._data_thread.finished.connect(self._data_thread.deleteLater)
        self._data_thread.finished.connect(self._data_worker.deleteLater)
        self._data_thread.start()

    def _on_data_loaded(self, payload: Dict[str, Any]) -> None:
        self._set_loading_state(False)

        user_info = payload.get("user", {})
        username = user_info.get("username") or self._username or "Authenticated User"
        self.top_bar.set_user_display(username, user_id=self._user_id)
        resolved_global_role = user_info.get("global_role") or self._global_role or "USER"
        self.top_bar.set_user_role("Administrator" if str(resolved_global_role).upper() == "ADMIN" else "Secure Operator")

        server_online = payload.get("server_online", False)
        self.top_bar.set_server_status("Online" if server_online else "Offline", "online" if server_online else "offline")
        self.top_bar.set_subtitle(payload.get("server_message", "Overview ready."))

        stats = payload.get("stats", {})
        self.rooms_stat.set_value(str(stats.get("room_count", 0)))
        self.files_stat.set_value(str(stats.get("file_count", 0)))
        self.members_stat.set_value(str(stats.get("member_count", 0)))
        self.status_stat.set_value(stats.get("server_label", "Unknown"))
        self.status_stat.set_subtitle("Coordinator backend health and transport status.")

        backend_rooms = list(payload.get("rooms", []))
        self._recent_rooms = RecentRoomsStore.sync_with_valid_rooms(backend_rooms)
        self.rooms_loaded.emit(backend_rooms)
        self._render_recent_rooms(self._recent_rooms)
        self._remote_activities = list(payload.get("activities", []))
        self._render_activities(self._current_activity_feed())

    def _on_data_failed(self, message: str) -> None:
        self._set_loading_state(False)
        self.top_bar.set_server_status("Offline", "offline")
        self.top_bar.set_subtitle("Unable to load secure workspace data.")
        self.error_toast.move_to_top_center(self)
        self.error_toast.show_error(message)
        self._render_recent_rooms(self._recent_rooms)
        self._remote_activities = []
        self._render_activities(self._current_activity_feed())

    def set_recent_rooms(self, rooms: list[dict[str, Any]]) -> None:
        self._recent_rooms = list(rooms)
        self._render_recent_rooms(self._recent_rooms)

    def set_local_activities(self, activities: list[dict[str, Any]]) -> None:
        self._local_activities = list(activities)
        self._render_activities(self._current_activity_feed())

    def _current_activity_feed(self) -> list[dict[str, Any]]:
        return list(self._remote_activities) if self._remote_activities else list(self._local_activities)

    def _render_recent_rooms(self, rooms: list[dict[str, Any]]) -> None:
        while self.rooms_content.count():
            item = self.rooms_content.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._room_cards.clear()

        if not rooms:
            self.rooms_content.addStretch()
            self.rooms_content.addWidget(
                EmptyState(
                    title="No recently opened rooms yet.",
                    message="Open a room from My Rooms to see it here.",
                    minimal=True,
                )
            )
            self.rooms_content.addStretch()
            return

        for room in rooms[:3]:
            card = RoomCard()
            card.set_room_data(room)
            card.open_requested.connect(
                lambda _room_id, room_payload=room: self.room_open_requested.emit(
                    {
                        **room_payload,
                        "username": self._username,
                        "email": self._email,
                        "global_role": self._global_role,
                        "current_username": self._username,
                        "current_user_id": self._user_id,
                    }
                )
            )
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
            self.activity_content.addWidget(
                EmptyState(
                    title="No recent activity yet.",
                    message="No recent activity yet.",
                    minimal=True,
                )
            )
            return

        for activity in activities:
            item = ActivityItem(
                activity_type=activity.get("type", "Activity"),
                message=activity.get("message", ""),
                timestamp=activity.get("timestamp", ""),
            )
            self.activity_content.addWidget(item)
            self._activity_widgets.append(item)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._data_thread and self._data_thread.isRunning():
            self._data_thread.quit()
            self._data_thread.wait(2000)
        super().closeEvent(event)


__all__ = ["OverviewPage"]
