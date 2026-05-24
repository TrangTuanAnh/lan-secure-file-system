"""My Rooms content page with threaded backend integration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget, QLabel

from services.services import BackendService
from ui.dashboard_runtime import DashboardRuntimeConfig
from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.create_room_dialog import CreateRoomDialog
from ui.widgets.empty_state import EmptyState
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.room_card import RoomCard
from ui.widgets.top_bar import TopBar


class RoomsLoadWorker(QObject):
    """Fetch all accessible rooms in a background thread."""

    success = Signal(list)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str = "") -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return

            if self._token:
                service._client.set_token(self._token)

            rooms = service.rooms.get_rooms()
            normalized: list[dict[str, Any]] = []
            for room in rooms:
                normalized.append(
                    {
                        "room_id": room.get("roomId") or room.get("id") or "",
                        "room_name": room.get("name") or room.get("roomName") or "Untitled Room",
                        "role": room.get("role") or room.get("memberRole") or room.get("myRole") or room.get("permission") or "Member",
                        "member_count": int(room.get("memberCount") or room.get("membersCount") or 0),
                        "file_count": int(room.get("fileCount") or 0),
                        "summary": room.get("description")
                        or room.get("summary")
                        or "Secure collaborative room with encrypted document access.",
                        "last_activity": room.get("lastActivity") or room.get("updatedAt") or "No recent activity recorded.",
                    }
                )
            self.success.emit(normalized)
        except TimeoutError:
            self.failure.emit("Room list request timed out. Please try again.")
        except Exception as exc:
            self.failure.emit(f"Failed to load rooms: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class CreateRoomWorker(QObject):
    """Create a room in the background and return the backend payload."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str, room_name: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._room_name = room_name

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return

            if self._token:
                service._client.set_token(self._token)

            created = service.rooms.create_room(self._room_name)
            if not created:
                self.failure.emit("Unable to create room. Please try again.")
                return
            self.success.emit(created)
        except TimeoutError:
            self.failure.emit("Room creation timed out. Please try again.")
        except Exception as exc:
            self.failure.emit(f"Failed to create room: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class MyRoomsPage(QWidget):
    """Authenticated room listing page with create room flow."""

    room_open_requested = Signal(str)

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
        self._load_thread: Optional[QThread] = None
        self._load_worker: Optional[RoomsLoadWorker] = None
        self._create_thread: Optional[QThread] = None
        self._create_worker: Optional[CreateRoomWorker] = None
        self._room_cards: list[RoomCard] = []
        self._create_dialog: Optional[CreateRoomDialog] = None

        self._build_ui()
        self._apply_styles()
        self.reload_rooms()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        self.error_toast = ErrorLabel(parent=self)
        self.error_toast.move_to_top_center(self)

        self.top_bar = TopBar(
            page_title="My Rooms",
            subtitle="Loading your accessible secure rooms...",
            search_placeholder="Search rooms by name or summary",
            user_display=self._username or "Authenticated User",
        )
        self.top_bar.set_server_status("Loading", "warning")
        self.top_bar.search_changed.connect(self._filter_rooms)
        root.addWidget(self.top_bar)

        self.toolbar_frame = QFrame()
        self.toolbar_frame.setObjectName("roomsToolbar")
        toolbar_layout = QHBoxLayout(self.toolbar_frame)
        toolbar_layout.setContentsMargins(20, 18, 20, 18)
        toolbar_layout.setSpacing(14)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(4)
        title = QLabel("Accessible Rooms")
        title.setObjectName("roomsToolbarTitle")
        title.setFont(app_font(14, 700))
        text_column.addWidget(title)
        subtitle = QLabel("Browse rooms you can access and create new secure collaboration spaces.")
        subtitle.setObjectName("roomsToolbarSubtitle")
        subtitle.setFont(ui_font(9))
        subtitle.setWordWrap(True)
        text_column.addWidget(subtitle)
        toolbar_layout.addLayout(text_column, 1)

        self.refresh_button = ModernButton("Refresh Rooms")
        self.refresh_button.clicked.connect(self.reload_rooms)
        toolbar_layout.addWidget(self.refresh_button)

        self.create_room_button = ModernButton("Create Room")
        self.create_room_button.set_accent_color(PALETTE.accent_soft)
        self.create_room_button.clicked.connect(self._open_create_dialog)
        toolbar_layout.addWidget(self.create_room_button)
        root.addWidget(self.toolbar_frame)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("roomsScrollArea")
        root.addWidget(self.scroll_area, 1)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("roomsScrollContent")
        self.rooms_layout = QVBoxLayout(self.scroll_content)
        self.rooms_layout.setContentsMargins(0, 0, 0, 12)
        self.rooms_layout.setSpacing(14)
        self.scroll_area.setWidget(self.scroll_content)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#roomsToolbar {{
                background-color: rgba(26, 26, 46, 216);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 22px;
            }}
            QScrollArea#roomsScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget#roomsScrollContent {{
                background: transparent;
            }}
            QLabel {{
                background: transparent;
                font-family: "{ui_font_family()}";
            }}
            QLabel#roomsToolbarTitle {{
                color: #f4fff9;
            }}
            QLabel#roomsToolbarSubtitle {{
                color: #8aa39a;
            }}
            """
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_toast.move_to_top_center(self)

    def _set_loading_state(self, loading: bool) -> None:
        self.refresh_button.set_loading(loading, "Loading" if loading else None)
        if not loading:
            self.refresh_button.set_loading(False)
        self.create_room_button.setEnabled(not loading)
        self.top_bar.search_input.setEnabled(not loading)

    def reload_rooms(self) -> None:
        if self._load_thread and self._load_thread.isRunning():
            return

        self._set_loading_state(True)
        self.error_toast.hide_error()
        self.top_bar.set_subtitle("Loading your accessible secure rooms...")
        self.top_bar.set_server_status("Loading", "warning")

        self._load_thread = QThread(self)
        self._load_worker = RoomsLoadWorker(self._runtime, token=self._token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.success.connect(self._on_rooms_loaded)
        self._load_worker.failure.connect(self._on_rooms_failed)
        self._load_worker.success.connect(self._load_thread.quit)
        self._load_worker.failure.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._load_thread.deleteLater)
        self._load_thread.finished.connect(self._load_worker.deleteLater)
        self._load_thread.start()

    def _on_rooms_loaded(self, rooms: list[dict[str, Any]]) -> None:
        self._set_loading_state(False)
        self.top_bar.set_server_status("Online", "online")
        self.top_bar.set_subtitle(f"{len(rooms)} room(s) available to your authenticated session.")
        self._render_rooms(rooms)

    def _on_rooms_failed(self, message: str) -> None:
        self._set_loading_state(False)
        self.top_bar.set_server_status("Offline", "offline")
        self.top_bar.set_subtitle("Unable to load room inventory.")
        self.error_toast.move_to_top_center(self)
        self.error_toast.show_error(message)
        self._render_rooms([])

    def _render_rooms(self, rooms: list[dict[str, Any]]) -> None:
        while self.rooms_layout.count():
            item = self.rooms_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._room_cards.clear()

        if not rooms:
            empty = EmptyState(
                title="No rooms yet",
                message="You do not have access to any rooms yet. Create a secure room to get started.",
                action_text="Create Room",
            )
            empty.action_requested.connect(self._open_create_dialog)
            self.rooms_layout.addWidget(empty)
            return

        for room in rooms:
            card = RoomCard()
            card.set_room_data(room)
            card.open_requested.connect(self.room_open_requested.emit)
            self.rooms_layout.addWidget(card)
            self._room_cards.append(card)

        self.rooms_layout.addStretch()

    def _filter_rooms(self, query: str) -> None:
        normalized = query.strip().lower()
        for card in self._room_cards:
            room_name = card.room_name_label.text().lower()
            summary = card.summary_label.text().lower()
            matches = not normalized or normalized in room_name or normalized in summary
            card.setVisible(matches)

    def _open_create_dialog(self) -> None:
        if self._create_dialog is None:
            self._create_dialog = CreateRoomDialog(self)
            self._create_dialog.create_requested.connect(self._start_create_room)
        self._create_dialog.room_name_input.clear()
        self._create_dialog.error_label.hide_error()
        self._create_dialog.show()
        self._create_dialog.raise_()
        self._create_dialog.activateWindow()

    def _start_create_room(self, room_name: str) -> None:
        if self._create_thread and self._create_thread.isRunning():
            return

        if self._create_dialog is not None:
            self._create_dialog.set_loading(True)

        self._create_thread = QThread(self)
        self._create_worker = CreateRoomWorker(self._runtime, self._token, room_name)
        self._create_worker.moveToThread(self._create_thread)
        self._create_thread.started.connect(self._create_worker.run)
        self._create_worker.success.connect(self._on_room_created)
        self._create_worker.failure.connect(self._on_room_create_failed)
        self._create_worker.success.connect(self._create_thread.quit)
        self._create_worker.failure.connect(self._create_thread.quit)
        self._create_thread.finished.connect(self._create_thread.deleteLater)
        self._create_thread.finished.connect(self._create_worker.deleteLater)
        self._create_thread.start()

    def _on_room_created(self, payload: dict[str, Any]) -> None:
        if self._create_dialog is not None:
            self._create_dialog.set_loading(False)
            self._create_dialog.accept()
        room_name = payload.get("name") or payload.get("roomName") or "Room"
        self.error_toast.move_to_top_center(self)
        self.error_toast.show_error(f"Room '{room_name}' created successfully.")
        self.reload_rooms()

    def _on_room_create_failed(self, message: str) -> None:
        if self._create_dialog is not None:
            self._create_dialog.set_loading(False)
            self._create_dialog.error_label.move_to_top_center(self._create_dialog)
            self._create_dialog.error_label.show_error(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(2000)
        if self._create_thread and self._create_thread.isRunning():
            self._create_thread.quit()
            self._create_thread.wait(2000)
        super().closeEvent(event)


__all__ = ["MyRoomsPage"]
