"""File-centric room page rendered inside the dashboard shell."""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from network.storage_node_data_plane import DataPlaneError, StorageNodeDataPlaneClient
from services.services import BackendService
from ui.dashboard_runtime import DashboardRuntimeConfig
from ui.fonts import app_font, load_app_fonts, ui_font, ui_font_family
from ui.widgets.error_label import ErrorLabel
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.modern_lineedit import ModernLineEdit
from ui.widgets.room_members_drawer import RoomMembersDrawer
from ui.widgets.status_badge import StatusBadge
from ui.widgets.top_bar import TopBar


ROLE_OPTIONS = ("OWNER", "MEMBER", "VIEWER")
logger = logging.getLogger(__name__)


def _format_timestamp(value: Any) -> str:
    if value in (None, "", 0):
        return "Unknown"
    return str(value)


def _format_size(size_value: Any) -> str:
    try:
        size = int(size_value or 0)
    except (TypeError, ValueError):
        return "Unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    display = float(size)
    while display >= 1024 and unit_index < len(units) - 1:
        display /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(display)} {units[unit_index]}"
    return f"{display:.1f} {units[unit_index]}"


def _normalize_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": member.get("userId") or member.get("user_id") or member.get("id") or "",
        "username": member.get("username") or "Unknown User",
        "email": member.get("email") or "No email",
        "role": str(member.get("role") or "").upper(),
        "joined_at": member.get("addedAt") or member.get("joinedAt") or member.get("joined_at") or "",
    }


def _normalize_file(file_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": file_payload.get("fileId") or file_payload.get("file_id") or "",
        "room_id": file_payload.get("roomId") or file_payload.get("room_id") or "",
        "name": file_payload.get("name") or file_payload.get("originalName") or "Unnamed File",
        "original_name": file_payload.get("originalName") or file_payload.get("name") or "Unnamed File",
        "uploader_id": file_payload.get("uploaderId") or file_payload.get("uploader_id") or "",
        "size": file_payload.get("size") or file_payload.get("sizeBytes") or 0,
        "status": file_payload.get("status") or "UNKNOWN",
        "version": file_payload.get("version") or file_payload.get("currentVersion") or 1,
        "uploaded_by": file_payload.get("uploadedBy") or file_payload.get("uploaderUsername") or file_payload.get("uploader") or "Unknown",
        "uploaded_at": file_payload.get("uploadedAt") or file_payload.get("createdAt") or "",
        "sha256_hash": file_payload.get("sha256Hash") or file_payload.get("sha256Whole") or "",
        "mime_type": file_payload.get("mimeType") or "",
        "scan_status": file_payload.get("scanStatus") or "",
        "scan_time": file_payload.get("scanTime") or "",
        "description": file_payload.get("description") or "",
    }


def _file_status_variant(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"ready", "clean", "completed", "active"}:
        return "active"
    if normalized in {"scanning", "pending", "queued"}:
        return "warning"
    if normalized in {"infected", "blocked", "failed", "error"}:
        return "offline"
    return "active"


class FileListCard(QFrame):
    """Compact selectable file row with clean metadata only."""

    clicked = Signal(dict)

    def __init__(self, file_data: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._file_data = dict(file_data)
        self.setObjectName("fileListCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(82)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        self.name_label = QLabel(self._file_data.get("name", "Unnamed File"))
        self.name_label.setFont(app_font(11, 600))
        self.name_label.setWordWrap(True)
        header_row.addWidget(self.name_label, 1)

        status_text = self._file_data.get("scan_status") or self._file_data.get("status") or ""
        self.status_badge = StatusBadge(status_text or "READY", _file_status_variant(str(status_text)))
        self.status_badge.setVisible(bool(status_text))
        header_row.addWidget(self.status_badge, 0, Qt.AlignTop)
        layout.addLayout(header_row)

        meta_text = f"{_format_size(self._file_data.get('size'))} · Uploaded by {self._file_data.get('uploaded_by', 'Unknown')}"
        self.meta_label = QLabel(meta_text)
        self.meta_label.setObjectName("fileCardMeta")
        self.meta_label.setFont(ui_font(9))
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        self.version_label = QLabel(f"Version {self._file_data.get('version', 1)}")
        self.version_label.setObjectName("fileCardSubtle")
        self.version_label.setFont(ui_font(9, 600))
        layout.addWidget(self.version_label)

        self.setToolTip(self._file_data.get("name", "Unnamed File"))
        self.set_selected(False)

    @property
    def file_data(self) -> dict[str, Any]:
        return dict(self._file_data)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_data)
            event.accept()
            return
        super().mousePressEvent(event)


class BaseRoomDialog(QDialog):
    """Shared room management dialog styling."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setObjectName("roomDialog")
        self.setMinimumWidth(520)
        self.error_label = ErrorLabel(parent=self)

        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(24, 22, 24, 22)
        self.layout_root.setSpacing(14)

        title_label = QLabel(title)
        title_label.setFont(app_font(15, 700))
        self.layout_root.addWidget(title_label)

        self.setStyleSheet(
            f"""
            QDialog#roomDialog {{
                background-color: rgba(15, 15, 30, 246);
                border: 1px solid rgba(0, 200, 83, 42);
                border-radius: 24px;
            }}
            QFrame#dialogCard,
            QFrame#dialogRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#dialogSubtitle,
            QLabel#fieldLabel,
            QLabel#memberMeta,
            QLabel#memberHint {{
                color: #8aa39a;
            }}
            """
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_label.move_to_top_center(self)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(app_font(10, 600))
        return label


class AddMemberDialog(BaseRoomDialog):
    """Collect backend-supported member data."""

    submitted = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Add Room Member", parent)

        subtitle = QLabel("Enter the user's UUID. The user can copy it from Account profile.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setFont(ui_font(9))
        self.layout_root.addWidget(subtitle)

        self.layout_root.addWidget(self._field_label("User ID"))
        self.user_id_input = ModernLineEdit("Enter user UUID")
        self.layout_root.addWidget(self.user_id_input)

        self.layout_root.addWidget(self._field_label("Role"))
        self.role_input = ModernLineEdit("OWNER, MEMBER, or VIEWER")
        self.role_input.setText("MEMBER")
        self.layout_root.addWidget(self.role_input)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.cancel_button = ModernButton("Cancel")
        self.cancel_button.set_button_style(background_color=PALETTE.surface, background_alt=PALETTE.surface_alt)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)

        self.confirm_button = ModernButton("Add Member")
        self.confirm_button.clicked.connect(self._submit)
        actions.addWidget(self.confirm_button)
        self.layout_root.addLayout(actions)

        self.user_id_input.returnPressed.connect(self._submit)

    def _submit(self) -> None:
        user_id = self.user_id_input.text().strip()
        role = self.role_input.text().strip().upper()
        if not user_id:
            self.error_label.show_error("Please enter a user ID.")
            return
        if role not in ROLE_OPTIONS:
            self.error_label.show_error("Role must be OWNER, MEMBER, or VIEWER.")
            return
        self.error_label.hide_error()
        self.submitted.emit(user_id, role)

    def set_loading(self, loading: bool) -> None:
        self.user_id_input.setEnabled(not loading)
        self.role_input.setEnabled(not loading)
        self.cancel_button.setEnabled(not loading)
        self.confirm_button.set_loading(loading, "Adding")


class SetRoleDialog(BaseRoomDialog):
    """Update member role using the existing backend SET_ROLE API."""

    submitted = Signal(str)

    def __init__(self, username: str, current_role: str, parent: Optional[QWidget] = None) -> None:
        super().__init__("Set Member Role", parent)
        subtitle = QLabel(f"Update room role for {username}.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setFont(ui_font(9))
        self.layout_root.addWidget(subtitle)

        self.layout_root.addWidget(self._field_label("Role"))
        self.role_input = ModernLineEdit("OWNER, MEMBER, or VIEWER")
        self.role_input.setText(current_role.upper() or "MEMBER")
        self.layout_root.addWidget(self.role_input)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.cancel_button = ModernButton("Cancel")
        self.cancel_button.set_button_style(background_color=PALETTE.surface, background_alt=PALETTE.surface_alt)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)

        self.confirm_button = ModernButton("Save Role")
        self.confirm_button.clicked.connect(self._submit)
        actions.addWidget(self.confirm_button)
        self.layout_root.addLayout(actions)

    def _submit(self) -> None:
        role = self.role_input.text().strip().upper()
        if role not in ROLE_OPTIONS:
            self.error_label.show_error("Role must be OWNER, MEMBER, or VIEWER.")
            return
        self.error_label.hide_error()
        self.submitted.emit(role)

    def set_loading(self, loading: bool) -> None:
        self.role_input.setEnabled(not loading)
        self.cancel_button.setEnabled(not loading)
        self.confirm_button.set_loading(loading, "Saving")


class FileVersionsDialog(BaseRoomDialog):
    """Show version history if FILE_VERSIONS is supported."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("File Versions", parent)
        self.subtitle = QLabel("Version history for the selected file.")
        self.subtitle.setObjectName("dialogSubtitle")
        self.subtitle.setFont(ui_font(9))
        self.layout_root.addWidget(self.subtitle)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.layout_root.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(10)
        self.scroll.setWidget(self.content)

        close_button = ModernButton("Close")
        close_button.clicked.connect(self.accept)
        self.layout_root.addWidget(close_button, 0, Qt.AlignRight)

    def set_versions(self, file_name: str, versions: list[dict[str, Any]]) -> None:
        self.subtitle.setText(f"Version history for {file_name}.")
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not versions:
            label = QLabel("No versions returned by backend.")
            label.setObjectName("dialogSubtitle")
            self.rows.addWidget(label)
            return

        for version in versions:
            row = QFrame()
            row.setObjectName("dialogRow")
            layout = QVBoxLayout(row)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(4)
            title = QLabel(f"Version {version.get('version', '--')}")
            title.setFont(app_font(11, 600))
            layout.addWidget(title)
            meta = QLabel(
                f"Uploader: {version.get('uploadedBy') or version.get('uploaderUsername') or 'Unknown'}"
                f"   |   Uploaded at: {_format_timestamp(version.get('uploadedAt') or version.get('createdAt'))}"
            )
            meta.setObjectName("memberMeta")
            meta.setFont(ui_font(9))
            layout.addWidget(meta)
            hash_label = QLabel(f"SHA-256: {version.get('sha256Hash') or version.get('sha256Whole') or 'Unavailable'}")
            hash_label.setObjectName("memberMeta")
            hash_label.setWordWrap(True)
            hash_label.setFont(ui_font(9))
            layout.addWidget(hash_label)
            self.rows.addWidget(row)
        self.rows.addStretch()


class MembersDialog(BaseRoomDialog):
    """Secondary dialog for room membership and permissions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Room Members", parent)
        self.subtitle = QLabel("Member access and room roles.")
        self.subtitle.setObjectName("dialogSubtitle")
        self.subtitle.setFont(ui_font(9))
        self.layout_root.addWidget(self.subtitle)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.summary_label = QLabel("Loading members...")
        self.summary_label.setObjectName("dialogSubtitle")
        self.summary_label.setFont(ui_font(9))
        header.addWidget(self.summary_label, 1)
        self.add_member_button = ModernButton("Add Member")
        header.addWidget(self.add_member_button)
        self.layout_root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.layout_root.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(10)
        self.scroll.setWidget(self.content)

        close_button = ModernButton("Close")
        close_button.clicked.connect(self.accept)
        self.layout_root.addWidget(close_button, 0, Qt.AlignRight)


class RoomDataWorker(QObject):
    """Load members and files for a room off the GUI thread."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str, room_id: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._room_id = room_id

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return
            if self._token:
                service._client.set_token(self._token)

            members = [_normalize_member(member) for member in service.rooms.get_room_members(self._room_id)]
            files = [_normalize_file(file_data) for file_data in service.files.get_files(self._room_id)]
            self.success.emit({"members": members, "files": files})
        except TimeoutError:
            self.failure.emit("Room data request timed out. Please try again.")
        except Exception as exc:
            self.failure.emit(f"Failed to load room data: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class FileDetailWorker(QObject):
    """Load FILE_DETAIL safely in the background."""

    success = Signal(dict)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str, file_id: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._file_id = file_id

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server for file detail.")
                return
            if self._token:
                service._client.set_token(self._token)
            detail = service.files.get_file_detail(self._file_id)
            if not detail:
                self.failure.emit("File detail is not available.")
                return
            self.success.emit(_normalize_file(detail))
        except Exception as exc:
            self.failure.emit(f"Failed to load file detail: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class MemberActionWorker(QObject):
    """Run room member operations without blocking the GUI thread."""

    success = Signal(str)
    failure = Signal(str)

    def __init__(
        self,
        runtime: DashboardRuntimeConfig,
        token: str,
        action: str,
        room_id: str,
        user_id: str = "",
        role: str = "",
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._action = action
        self._room_id = room_id
        self._user_id = user_id
        self._role = role

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server. Please verify the coordinator service is running.")
                return
            if self._token:
                service._client.set_token(self._token)

            if self._action == "add":
                if not service.rooms.add_member(self._room_id, self._user_id, self._role):
                    self.failure.emit("Unable to add member. Check permission, user ID, or duplicate membership.")
                    return
                self.success.emit("Member added successfully.")
                return

            if self._action == "remove":
                if not service.rooms.remove_member(self._room_id, self._user_id):
                    self.failure.emit("Unable to remove member. Check permission or membership status.")
                    return
                self.success.emit("Member removed successfully.")
                return

            if self._action == "set_role":
                if not service.rooms.set_member_role(self._room_id, self._user_id, self._role):
                    self.failure.emit("Unable to change member role. Check permission or selected role.")
                    return
                self.success.emit("Member role updated successfully.")
                return

            self.failure.emit("Unsupported member action.")
        except Exception as exc:
            self.failure.emit(f"Room member action failed: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class FileVersionsWorker(QObject):
    """Load FILE_VERSIONS from the service layer."""

    success = Signal(list)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str, room_id: str, original_name: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._room_id = room_id
        self._original_name = original_name

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server for file versions.")
                return
            if self._token:
                service._client.set_token(self._token)
            versions = service.files.get_file_versions(self._room_id, self._original_name)
            self.success.emit(list(versions))
        except Exception as exc:
            self.failure.emit(f"Failed to load file versions: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class FileDeleteWorker(QObject):
    """Delete a file through the service layer."""

    success = Signal(str)
    failure = Signal(str)

    def __init__(self, runtime: DashboardRuntimeConfig, token: str, file_id: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._file_id = file_id

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server for file deletion.")
                return
            if self._token:
                service._client.set_token(self._token)
            try:
                service._client.delete_file(self._file_id)
            except ValueError as exc:
                error_text = str(exc)
                if "PERMISSION_DENIED" in error_text:
                    self.failure.emit("You do not have permission to delete this file.")
                    return
                if "FILE_NOT_FOUND" in error_text:
                    self.failure.emit("This file no longer exists on the server.")
                    return
                self.failure.emit(f"Failed to delete file: {error_text}")
                return
            self.success.emit("File deleted successfully.")
        except Exception as exc:
            self.failure.emit(f"Failed to delete file: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class FileUploadWorker(QObject):
    """Run INIT_UPLOAD and Storage Node data transfer off the UI thread."""

    success = Signal(str)
    failure = Signal(str)

    def __init__(
        self,
        runtime: DashboardRuntimeConfig,
        token: str,
        room_id: str,
        file_path: str,
        uploader_id: str,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._room_id = room_id
        self._file_path = file_path
        self._uploader_id = uploader_id

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            source_path = Path(self._file_path)
            file_bytes = source_path.read_bytes()
            whole_hash = hashlib.sha256(file_bytes).hexdigest()

            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server for upload.")
                return
            if self._token:
                service._client.set_token(self._token)

            plan = service.upload.init_upload(
                self._room_id,
                source_path.name,
                len(file_bytes),
                whole_hash,
            )
            if not plan:
                self.failure.emit("Unable to initialize upload.")
                return
            logger.info("INIT_UPLOAD returned storage target: %s", plan.get("storageAddress"))
            if plan.get("deduplicated"):
                self.success.emit(f"File '{source_path.name}' already exists and was deduplicated.")
                return

            transfer_client = StorageNodeDataPlaneClient(str(plan.get("storageAddress") or ""))
            transfer_client.upload_file(
                plan=plan,
                file_path=self._file_path,
                uploader_id=self._uploader_id,
            )
            self.success.emit(f"File '{source_path.name}' uploaded successfully.")
        except DataPlaneError as exc:
            self.failure.emit(str(exc))
        except Exception as exc:
            self.failure.emit(f"Failed to upload file: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class FileDownloadWorker(QObject):
    """Run INIT_DOWNLOAD and Storage Node file retrieval off the UI thread."""

    success = Signal(str)
    failure = Signal(str)

    def __init__(
        self,
        runtime: DashboardRuntimeConfig,
        token: str,
        file_id: str,
        file_name: str,
        version: int,
        downloader_id: str,
        save_path: str,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._token = token
        self._file_id = file_id
        self._file_name = file_name
        self._version = version
        self._downloader_id = downloader_id
        self._save_path = save_path

    def run(self) -> None:
        service: Optional[BackendService] = None
        try:
            service = BackendService(self._runtime.to_backend_config())
            if not service.connect():
                self.failure.emit("Cannot reach server for download.")
                return
            if self._token:
                service._client.set_token(self._token)

            plan = service.download.init_download(self._file_id, version=self._version)
            if not plan:
                self.failure.emit("Unable to initialize download.")
                return
            plan["fileId"] = self._file_id
            logger.info("INIT_DOWNLOAD returned storage target: %s", plan.get("storageAddress"))

            transfer_client = StorageNodeDataPlaneClient(str(plan.get("storageAddress") or ""))
            transfer_client.download_file(
                plan=plan,
                save_path=self._save_path,
                downloader_id=self._downloader_id,
            )
            self.success.emit(f"Saved '{self._file_name}' to {self._save_path}.")
        except DataPlaneError as exc:
            self.failure.emit(str(exc))
        except Exception as exc:
            self.failure.emit(f"Failed to download file: {exc}")
        finally:
            if service and service.is_connected():
                service.disconnect()


class RoomPage(QWidget):
    """Primary room content focused on secure file management."""

    back_requested = Signal()

    def __init__(
        self,
        room_data: dict[str, Any],
        username: str,
        user_id: str,
        email: str,
        token: str,
        global_role: str,
        runtime: DashboardRuntimeConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._username = username
        self._user_id = user_id
        self._email = email
        self._token = token
        self._global_role = global_role.upper()
        self._room_data = dict(room_data)
        self._room_role = str(room_data.get("role") or room_data.get("memberRole") or "").upper()
        self._current_user_id = str(room_data.get("current_user_id") or user_id or room_data.get("user_id") or "").strip()
        self._current_username = str(room_data.get("current_username") or username or "").strip()

        self._data_thread: Optional[QThread] = None
        self._data_worker: Optional[RoomDataWorker] = None
        self._detail_thread: Optional[QThread] = None
        self._detail_worker: Optional[FileDetailWorker] = None
        self._member_thread: Optional[QThread] = None
        self._member_worker: Optional[MemberActionWorker] = None
        self._versions_thread: Optional[QThread] = None
        self._versions_worker: Optional[FileVersionsWorker] = None
        self._delete_thread: Optional[QThread] = None
        self._delete_worker: Optional[FileDeleteWorker] = None
        self._upload_thread: Optional[QThread] = None
        self._upload_worker: Optional[FileUploadWorker] = None
        self._download_thread: Optional[QThread] = None
        self._download_worker: Optional[FileDownloadWorker] = None

        self._members: list[dict[str, Any]] = []
        self._files: list[dict[str, Any]] = []
        self._filtered_files: list[dict[str, Any]] = []
        self._selected_file: dict[str, Any] = {}
        self._file_cards: list[FileListCard] = []
        self._pending_uploaded_file_name: str = ""
        self._pending_delete_file: dict[str, Any] = {}
        self._members_drawer: Optional[RoomMembersDrawer] = None
        self._set_role_dialog: Optional[SetRoleDialog] = None
        self._versions_dialog: Optional[FileVersionsDialog] = None

        self._build_ui()
        self._apply_styles()
        self.reload_room_data()

    @property
    def room_id(self) -> str:
        return str(self._room_data.get("room_id") or self._room_data.get("roomId") or "")

    @property
    def room_name(self) -> str:
        return str(self._room_data.get("room_name") or self._room_data.get("name") or "Untitled Room")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        self.error_toast = ErrorLabel(parent=self)
        self.error_toast.move_to_top_center(self)

        self.top_bar = TopBar(
            page_title=f"My Rooms / {self.room_name}",
            subtitle=f"Room ID: {self.room_id or 'Unavailable'}",
            search_placeholder="Search files by name, uploader, or status",
            user_display=self._username or "Authenticated User",
            show_refresh_button=True,
        )
        self.top_bar.set_user_role(self._display_global_role())
        self.top_bar.search_changed.connect(self._filter_files)
        self.top_bar.refresh_requested.connect(self.reload_room_data)
        root.addWidget(self.top_bar)

        toolbar = QFrame()
        toolbar.setObjectName("roomActionToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 16, 20, 16)
        toolbar_layout.setSpacing(12)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        title = QLabel(self.room_name)
        title.setObjectName("sectionTitle")
        title.setFont(app_font(14, 700))
        info_col.addWidget(title)

        subtitle = QLabel("Secure room file inventory and member access controls.")
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setFont(ui_font(9))
        subtitle.setWordWrap(True)
        info_col.addWidget(subtitle)
        toolbar_layout.addLayout(info_col, 1)

        self.back_button = ModernButton("Back to Rooms")
        self.back_button.clicked.connect(self.back_requested.emit)
        toolbar_layout.addWidget(self.back_button)

        self.members_button = ModernButton("Members")
        self.members_button.clicked.connect(self._open_members_dialog)
        toolbar_layout.addWidget(self.members_button)

        self.upload_button = ModernButton("Upload File")
        self.upload_button.clicked.connect(self._open_upload_dialog)
        self.upload_button.setVisible(self._can_upload_files())
        toolbar_layout.addWidget(self.upload_button)

        self.delete_room_button = ModernButton("Delete Room")
        self.delete_room_button.setVisible(False)
        self.delete_room_button.setEnabled(False)
        self.delete_room_button.setToolTip("Delete room is not supported by backend yet.")
        toolbar_layout.addWidget(self.delete_room_button)
        root.addWidget(toolbar)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(18)
        root.addLayout(content_row, 1)

        self.files_section = self._build_section_frame("Files", "Protected files available in this room.")
        files_body = self.files_section["body"]

        self.files_empty_container = QWidget()
        empty_layout = QVBoxLayout(self.files_empty_container)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(0)
        empty_layout.addStretch()

        self.files_empty_label = QLabel("No files available in this room.")
        self.files_empty_label.setObjectName("emptyFilesLabel")
        self.files_empty_label.setWordWrap(True)
        self.files_empty_label.setAlignment(Qt.AlignCenter)
        self.files_empty_label.setFont(ui_font(10))
        empty_layout.addWidget(self.files_empty_label, 0, Qt.AlignCenter)
        empty_layout.addStretch()
        files_body.addWidget(self.files_empty_container, 1)

        self.files_scroll = QScrollArea()
        self.files_scroll.setObjectName("filesScroll")
        self.files_scroll.setWidgetResizable(True)
        self.files_scroll.setFrameShape(QFrame.NoFrame)
        self.files_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.files_list_content = QWidget()
        self.files_list_content.setObjectName("filesListContent")
        self.files_list_layout = QVBoxLayout(self.files_list_content)
        self.files_list_layout.setContentsMargins(0, 0, 0, 0)
        self.files_list_layout.setSpacing(10)
        self.files_list_layout.addStretch()

        self.files_scroll.setWidget(self.files_list_content)
        files_body.addWidget(self.files_scroll, 1)
        content_row.addWidget(self.files_section["frame"], 3)

        self.detail_card = QFrame()
        self.detail_card.setObjectName("fileDetailCard")
        self.detail_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(12)

        detail_title = QLabel("File Detail")
        detail_title.setObjectName("sectionTitle")
        detail_title.setFont(app_font(14, 700))
        detail_layout.addWidget(detail_title)

        self.file_detail_title = QLabel("Select a file")
        self.file_detail_title.setFont(app_font(13, 600))
        self.file_detail_title.setWordWrap(True)
        detail_layout.addWidget(self.file_detail_title)

        self.file_detail_lines: dict[str, QLabel] = {}
        for key in (
            "uploaded_by",
            "size",
            "status",
            "version",
            "sha256_hash",
            "uploaded_at",
            "mime_type",
            "scan_status",
            "description",
        ):
            line = QLabel("--")
            line.setObjectName("fileDetailMeta")
            line.setWordWrap(True)
            line.setFont(ui_font(9))
            self.file_detail_lines[key] = line
            detail_layout.addWidget(line)
        detail_layout.addStretch()

        detail_actions = QHBoxLayout()
        detail_actions.setContentsMargins(0, 0, 0, 0)
        detail_actions.setSpacing(10)

        self.download_button = ModernButton("Download")
        self.download_button.clicked.connect(self._start_download_selected)
        detail_actions.addWidget(self.download_button)

        self.delete_file_button = ModernButton("Delete")
        self.delete_file_button.set_accent_color(PALETTE.error)
        self.delete_file_button.clicked.connect(self._delete_selected_file)
        detail_actions.addWidget(self.delete_file_button)

        detail_layout.addLayout(detail_actions)
        content_row.addWidget(self.detail_card, 2)
        self._update_file_detail({})

        self.delete_confirm_panel = QFrame(self)
        self.delete_confirm_panel.setObjectName("deleteConfirmPanel")
        self.delete_confirm_panel.setFixedWidth(420)
        self.delete_confirm_panel.hide()

        confirm_layout = QVBoxLayout(self.delete_confirm_panel)
        confirm_layout.setContentsMargins(22, 20, 22, 20)
        confirm_layout.setSpacing(12)

        confirm_title = QLabel("Delete file?")
        confirm_title.setObjectName("sectionTitle")
        confirm_title.setFont(app_font(13, 700))
        confirm_layout.addWidget(confirm_title)

        self.delete_confirm_message = QLabel("Delete this file? This action cannot be undone.")
        self.delete_confirm_message.setObjectName("sectionSubtitle")
        self.delete_confirm_message.setWordWrap(True)
        self.delete_confirm_message.setFont(ui_font(9))
        confirm_layout.addWidget(self.delete_confirm_message)

        confirm_actions = QHBoxLayout()
        confirm_actions.setContentsMargins(0, 0, 0, 0)
        confirm_actions.setSpacing(10)

        self.delete_confirm_cancel = ModernButton("Cancel")
        self.delete_confirm_cancel.set_button_style(background_color=PALETTE.surface, background_alt=PALETTE.surface_alt)
        self.delete_confirm_cancel.clicked.connect(self._hide_delete_confirm_panel)
        confirm_actions.addWidget(self.delete_confirm_cancel)

        self.delete_confirm_accept = ModernButton("Delete")
        self.delete_confirm_accept.set_accent_color(PALETTE.error)
        self.delete_confirm_accept.clicked.connect(self._execute_delete_confirmed)
        confirm_actions.addWidget(self.delete_confirm_accept)

        confirm_layout.addLayout(confirm_actions)

    def _build_section_frame(self, title: str, subtitle: str) -> dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("roomSection")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setFont(app_font(14, 700))
        title_col.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("sectionSubtitle")
        subtitle_label.setWordWrap(True)
        subtitle_label.setFont(ui_font(9))
        title_col.addWidget(subtitle_label)
        header_row.addLayout(title_col, 1)
        layout.addLayout(header_row)

        body = QVBoxLayout()
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(12)
        layout.addLayout(body, 1)
        return {"frame": frame, "body": body}

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#roomActionToolbar,
            QFrame#roomSection,
            QFrame#fileDetailCard,
            QFrame#deleteConfirmPanel,
            QFrame#dialogRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 22px;
            }}
            QFrame#fileDetailCard {{
                background-color: rgba(15, 15, 30, 176);
                border-radius: 22px;
            }}
            QFrame#deleteConfirmPanel {{
                background-color: rgba(15, 15, 30, 244);
                border: 1px solid rgba(255, 82, 82, 0.35);
                border-radius: 20px;
            }}
            QScrollArea#filesScroll,
            QWidget#filesListContent {{
                background-color: transparent;
                border: none;
            }}
            QFrame#fileListCard {{
                background-color: rgba(15, 15, 30, 150);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QFrame#fileListCard:hover {{
                background-color: rgba(18, 30, 33, 186);
                border: 1px solid rgba(0, 230, 118, 0.30);
            }}
            QFrame#fileListCard[selected="true"] {{
                background-color: rgba(16, 38, 31, 208);
                border: 1px solid rgba(0, 230, 118, 0.58);
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#sectionTitle {{
                color: #f4fff9;
            }}
            QLabel#sectionSubtitle,
            QLabel#fileDetailMeta,
            QLabel#emptyFilesLabel,
            QLabel#fileCardMeta,
            QLabel#fileCardSubtle,
            QLabel#memberMeta,
            QLabel#memberHint {{
                color: #8aa39a;
            }}
            """
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.error_toast.move_to_top_center(self)
        if hasattr(self, "delete_confirm_panel"):
            panel_width = self.delete_confirm_panel.width()
            panel_x = max(24, (self.width() - panel_width) // 2)
            panel_y = max(140, (self.height() - self.delete_confirm_panel.sizeHint().height()) // 2)
            self.delete_confirm_panel.move(panel_x, panel_y)
        if self._members_drawer is not None:
            self._members_drawer.update_anchor_geometry()

    def _display_global_role(self) -> str:
        return "Administrator" if self._global_role == "ADMIN" else "Secure Operator"

    def _can_manage_members(self) -> bool:
        return self._global_role == "ADMIN" or self._room_role == "OWNER"

    def _can_upload_files(self) -> bool:
        return self._global_role == "ADMIN" or self._room_role in {"OWNER", "MEMBER"}

    def _can_delete_files(self) -> bool:
        return self._global_role == "ADMIN" or self._room_role == "OWNER"

    def _owner_count(self) -> int:
        return sum(1 for member in self._members if str(member.get("role", "")).upper() == "OWNER")

    def _is_current_member(self, member: dict[str, Any]) -> bool:
        member_user_id = str(member.get("user_id") or member.get("id") or "").strip()
        member_username = str(member.get("username") or "").strip().lower()
        if self._current_user_id and member_user_id:
            return member_user_id == self._current_user_id
        return bool(self._current_username) and member_username == self._current_username.lower()

    def _is_last_owner(self, member: dict[str, Any]) -> bool:
        return str(member.get("role", "")).upper() == "OWNER" and self._owner_count() == 1

    def _can_change_member_role(self, member: dict[str, Any]) -> bool:
        if not self._can_manage_members():
            return False
        if self._is_current_member(member):
            return False
        if self._is_last_owner(member):
            return False
        return bool(str(member.get("user_id") or "").strip())

    def _can_remove_member(self, member: dict[str, Any]) -> bool:
        if not self._can_manage_members():
            return False
        if self._is_current_member(member):
            return False
        if self._is_last_owner(member):
            return False
        return bool(str(member.get("user_id") or "").strip())

    def _member_action_hint(self, member: dict[str, Any]) -> str:
        hints: list[str] = []
        if self._is_current_member(member):
            hints.append("Current user")
        if self._is_last_owner(member):
            hints.append("Last owner")
        if hints:
            return " • ".join(hints)
        if not member.get("user_id"):
            return "User ID unavailable"
        return ""

    def _set_loading_state(self, loading: bool) -> None:
        self.top_bar.set_refresh_enabled(not loading)
        self.top_bar.search_input.setEnabled(not loading)
        self.back_button.setEnabled(not loading)
        self.members_button.setEnabled(not loading)
        self.upload_button.setEnabled(not loading and self._can_upload_files())

    def reload_room_data(self) -> None:
        if self._data_thread and self._data_thread.isRunning():
            return

        self._set_loading_state(True)
        self.error_toast.hide_error()
        self.top_bar.set_server_status("Loading", "warning")
        self.top_bar.set_subtitle(f"Room ID: {self.room_id or 'Unavailable'}")

        self._data_thread = QThread(self)
        self._data_worker = RoomDataWorker(self._runtime, self._token, self.room_id)
        self._data_worker.moveToThread(self._data_thread)
        self._data_thread.started.connect(self._data_worker.run)
        self._data_worker.success.connect(self._on_room_data_loaded)
        self._data_worker.failure.connect(self._on_room_data_failed)
        self._data_worker.success.connect(self._data_thread.quit)
        self._data_worker.failure.connect(self._data_thread.quit)
        self._data_thread.finished.connect(self._data_thread.deleteLater)
        self._data_thread.finished.connect(self._data_worker.deleteLater)
        self._data_thread.finished.connect(self._cleanup_data_thread)
        self._data_thread.start()

    def _is_file_uploader(self, file_data: dict[str, Any]) -> bool:
        uploader_id = str(file_data.get("uploader_id") or "").strip()
        if uploader_id and self._current_user_id:
            return uploader_id == self._current_user_id
        uploader_name = str(file_data.get("uploaded_by") or "").strip().lower()
        return bool(uploader_name and self._current_username) and uploader_name == self._current_username.lower()

    def _can_delete_file_item(self, file_data: dict[str, Any]) -> bool:
        if not file_data:
            return False
        if self._global_role == "ADMIN":
            return True
        if self._room_role == "OWNER":
            return True
        if self._room_role == "VIEWER":
            return False
        return self._is_file_uploader(file_data)

    def _on_room_data_loaded(self, payload: dict[str, Any]) -> None:
        self._set_loading_state(False)
        members = payload.get("members", [])
        files = payload.get("files", [])
        self._members = [dict(member) for member in members]
        self._files = [dict(file_item) for file_item in files]
        self.top_bar.set_server_status("Online", "online")
        self.top_bar.set_subtitle(f"{len(files)} file(s), {len(members)} member(s)")
        self._render_members_dialog()
        self._filter_files(self.top_bar.search_input.text())

    def _on_room_data_failed(self, message: str) -> None:
        self._set_loading_state(False)
        self.top_bar.set_server_status("Offline", "offline")
        self.top_bar.set_subtitle("Unable to load room inventory.")
        self.error_toast.show_error(message)
        self._members = []
        self._files = []
        self._render_members_dialog()
        self._render_file_cards([])

    def _filter_files(self, query: str) -> None:
        normalized = query.strip().lower()
        self._filtered_files = [
            file_item
            for file_item in self._files
            if not normalized
            or normalized in str(file_item.get("name", "")).lower()
            or normalized in str(file_item.get("uploaded_by", "")).lower()
            or normalized in str(file_item.get("status", "")).lower()
        ]
        self._render_file_cards(self._filtered_files)

    def _clear_file_cards(self) -> None:
        self._file_cards.clear()
        while self.files_list_layout.count():
            item = self.files_list_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    nested = child_layout.takeAt(0)
                    nested_widget = nested.widget()
                    if nested_widget is not None:
                        nested_widget.deleteLater()

    def _render_file_cards(self, files: list[dict[str, Any]]) -> None:
        self._clear_file_cards()
        self.files_empty_container.setVisible(not files)
        self.files_scroll.setVisible(bool(files))

        if not files:
            self._update_file_detail({})
            self._selected_file = {}
            return

        selected_file_id = str(self._selected_file.get("file_id") or "")
        selected_original_name = str(self._selected_file.get("original_name") or self._selected_file.get("name") or "")
        initial_selection: Optional[dict[str, Any]] = None

        for file_item in files:
            card = FileListCard(file_item, self.files_list_content)
            card.clicked.connect(self._on_file_selected)
            self.files_list_layout.addWidget(card)
            self._file_cards.append(card)

            if initial_selection is None:
                initial_selection = file_item

            file_id = str(file_item.get("file_id") or "")
            original_name = str(file_item.get("original_name") or file_item.get("name") or "")
            if self._pending_uploaded_file_name and self._pending_uploaded_file_name == original_name:
                initial_selection = file_item
            elif selected_file_id and selected_file_id == file_id:
                initial_selection = file_item
            elif not selected_file_id and selected_original_name and selected_original_name == original_name:
                initial_selection = file_item

        self.files_list_layout.addStretch()
        self._pending_uploaded_file_name = ""
        if initial_selection is not None:
            self._on_file_selected(initial_selection)

    def _update_file_card_selection(self, selected_file: dict[str, Any]) -> None:
        selected_id = str(selected_file.get("file_id") or "")
        selected_name = str(selected_file.get("original_name") or selected_file.get("name") or "")
        for card in self._file_cards:
            payload = card.file_data
            card_id = str(payload.get("file_id") or "")
            card_name = str(payload.get("original_name") or payload.get("name") or "")
            is_selected = bool(selected_id and card_id == selected_id) or (not selected_id and selected_name == card_name)
            card.set_selected(is_selected)

    def _on_file_selected(self, file_data: dict[str, Any]) -> None:
        self._selected_file = dict(file_data)
        self._update_file_card_selection(file_data)
        self._update_file_detail(file_data)
        file_id = str(file_data.get("file_id") or "")
        if not file_id or (self._detail_thread and self._detail_thread.isRunning()):
            return

        self._detail_thread = QThread(self)
        self._detail_worker = FileDetailWorker(self._runtime, self._token, file_id)
        self._detail_worker.moveToThread(self._detail_thread)
        self._detail_thread.started.connect(self._detail_worker.run)
        self._detail_worker.success.connect(self._on_file_detail_loaded)
        self._detail_worker.failure.connect(self._on_file_detail_failed)
        self._detail_worker.success.connect(self._detail_thread.quit)
        self._detail_worker.failure.connect(self._detail_thread.quit)
        self._detail_thread.finished.connect(self._detail_thread.deleteLater)
        self._detail_thread.finished.connect(self._detail_worker.deleteLater)
        self._detail_thread.finished.connect(self._cleanup_detail_thread)
        self._detail_thread.start()

    def _on_file_detail_loaded(self, detail: dict[str, Any]) -> None:
        self._update_file_detail(detail)

    def _on_file_detail_failed(self, _message: str) -> None:
        pass

    def _update_file_detail(self, detail: dict[str, Any]) -> None:
        self._selected_file = dict(detail)
        if not detail:
            self.file_detail_title.setText("Select a file")
            for key, label in self.file_detail_lines.items():
                label.setText(f"{key.replace('_', ' ').title()}: --")
            self.download_button.setEnabled(False)
            self.download_button.setToolTip("Select a file to download.")
            self.delete_file_button.setVisible(False)
            self.delete_file_button.setEnabled(False)
            self.file_detail_lines["description"].hide()
            return

        self.file_detail_title.setText(detail.get("name", "Unnamed File"))
        self.file_detail_lines["uploaded_by"].setText(f"Uploader: {detail.get('uploaded_by', 'Unknown')}")
        self.file_detail_lines["size"].setText(f"Size: {_format_size(detail.get('size'))}")
        self.file_detail_lines["status"].setText(f"Status: {detail.get('status', 'UNKNOWN')}")
        self.file_detail_lines["version"].setText(f"Version: {detail.get('version', 1)}")
        self.file_detail_lines["sha256_hash"].setText(f"SHA-256: {detail.get('sha256_hash') or 'Unavailable'}")
        self.file_detail_lines["uploaded_at"].setText(f"Uploaded at: {_format_timestamp(detail.get('uploaded_at'))}")
        self.file_detail_lines["mime_type"].setText(f"MIME type: {detail.get('mime_type') or 'Unknown'}")
        self.file_detail_lines["scan_status"].setText(
            f"Scan status: {detail.get('scan_status') or detail.get('status') or 'Unknown'}"
        )
        metadata_text = detail.get("description")
        if metadata_text and str(metadata_text).strip() not in {"{}", "[]"}:
            self.file_detail_lines["description"].setText(f"Metadata: {metadata_text}")
            self.file_detail_lines["description"].show()
        else:
            self.file_detail_lines["description"].clear()
            self.file_detail_lines["description"].hide()
        has_file_id = bool(str(detail.get("file_id") or "").strip())
        self.download_button.setEnabled(has_file_id)
        self.download_button.setToolTip("" if has_file_id else "Download is not supported by current backend yet.")
        can_delete_selected = has_file_id and self._can_delete_file_item(detail)
        self.delete_file_button.setVisible(can_delete_selected)
        self.delete_file_button.setEnabled(can_delete_selected)

    def _start_download_selected(self) -> None:
        if not self._selected_file:
            self.error_toast.show_error("Select a file before downloading.")
            return
        self._start_download(self._selected_file)

    def _delete_selected_file(self) -> None:
        if not self._selected_file:
            self.error_toast.show_error("Select a file before deleting.")
            return
        self._confirm_delete_file(self._selected_file)

    def _show_delete_confirm_panel(self, file_data: dict[str, Any]) -> None:
        self._pending_delete_file = dict(file_data)
        self.delete_confirm_message.setText(
            f"Delete {file_data.get('name', 'this file')}? This action cannot be undone."
        )
        self.delete_confirm_accept.set_loading(False)
        self.delete_confirm_panel.adjustSize()
        panel_width = self.delete_confirm_panel.width()
        panel_x = max(24, (self.width() - panel_width) // 2)
        panel_y = max(140, (self.height() - self.delete_confirm_panel.height()) // 2)
        self.delete_confirm_panel.move(panel_x, panel_y)
        self.delete_confirm_panel.show()
        self.delete_confirm_panel.raise_()

    def _hide_delete_confirm_panel(self) -> None:
        self.delete_confirm_accept.set_loading(False)
        self.delete_confirm_panel.hide()
        self._pending_delete_file = {}

    def _execute_delete_confirmed(self) -> None:
        file_data = dict(self._pending_delete_file)
        if not file_data:
            self._hide_delete_confirm_panel()
            return
        self.delete_confirm_accept.set_loading(True, "Deleting")
        self._start_delete_worker(file_data)

    def _ensure_members_drawer(self) -> RoomMembersDrawer:
        if self._members_drawer is None:
            parent_widget = self.window() if isinstance(self.window(), QWidget) else self
            self._members_drawer = RoomMembersDrawer(parent_widget)
            self._members_drawer.add_member_requested.connect(self._start_add_member)
            self._members_drawer.set_role_requested.connect(self._open_set_role_dialog)
            self._members_drawer.remove_member_requested.connect(self._confirm_remove_member)
        self._members_drawer.set_manage_permissions(self._can_manage_members())
        self._members_drawer.update_anchor_geometry()
        return self._members_drawer

    def _open_members_dialog(self) -> None:
        drawer = self._ensure_members_drawer()
        self._render_members_dialog()
        drawer.show_members_view()
        drawer.open()

    def _render_members_dialog(self) -> None:
        if self._members_drawer is None:
            return
        drawer_members: list[dict[str, Any]] = []
        for member in self._members:
            drawer_members.append(
                {
                    **member,
                    "can_set_role": self._can_change_member_role(member),
                    "can_remove": self._can_remove_member(member),
                    "hint": self._member_action_hint(member),
                    "tooltip_user_id": str(member.get("user_id") or "").strip(),
                }
            )
        self._members_drawer.set_manage_permissions(self._can_manage_members())
        self._members_drawer.set_members(drawer_members)

    def _open_add_member_dialog(self) -> None:
        if not self._can_manage_members():
            return
        drawer = self._ensure_members_drawer()
        drawer.prepare_add_member()
        drawer.open()

    def _open_set_role_dialog(self, member: dict[str, Any]) -> None:
        if not self._can_change_member_role(member):
            if self._is_current_member(member):
                self.error_toast.show_error("You cannot change your own role from this view.")
            elif self._is_last_owner(member):
                self.error_toast.show_error("The last owner cannot be demoted.")
            return
        self._set_role_dialog = SetRoleDialog(member.get("username", "Member"), member.get("role", ""), self)
        self._set_role_dialog.submitted.connect(lambda role: self._start_set_role(member, role))
        self._set_role_dialog.show()
        self._set_role_dialog.raise_()
        self._set_role_dialog.activateWindow()

    def _confirm_remove_member(self, member: dict[str, Any]) -> None:
        if not self._can_remove_member(member):
            if self._is_current_member(member):
                self.error_toast.show_error("You cannot remove your own account from this room here.")
            elif self._is_last_owner(member):
                self.error_toast.show_error("The last owner cannot be removed.")
            return
        confirm = QMessageBox.question(
            self,
            "Remove Member",
            f"Remove {member.get('username', 'this member')} from the room?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self._start_remove_member(member)

    def _run_member_action(self, action: str, user_id: str, role: str = "") -> None:
        if self._member_thread and self._member_thread.isRunning():
            return
        self.error_toast.hide_error()

        self._member_thread = QThread(self)
        self._member_worker = MemberActionWorker(
            self._runtime,
            self._token,
            action,
            self.room_id,
            user_id=user_id,
            role=role,
        )
        self._member_worker.moveToThread(self._member_thread)
        self._member_thread.started.connect(self._member_worker.run)
        self._member_worker.success.connect(self._on_member_action_success)
        self._member_worker.failure.connect(self._on_member_action_failed)
        self._member_worker.success.connect(self._member_thread.quit)
        self._member_worker.failure.connect(self._member_thread.quit)
        self._member_thread.finished.connect(self._member_thread.deleteLater)
        self._member_thread.finished.connect(self._member_worker.deleteLater)
        self._member_thread.finished.connect(self._cleanup_member_thread)
        self._member_thread.start()

    def _start_add_member(self, user_id: str, role: str) -> None:
        if not user_id.strip():
            return
        if self._members_drawer is not None:
            self._members_drawer.set_add_member_loading(True)
        self._run_member_action("add", user_id=user_id.strip(), role=role)

    def _start_set_role(self, member: dict[str, Any], role: str) -> None:
        if not self._can_change_member_role(member):
            return
        if self._set_role_dialog is not None:
            self._set_role_dialog.set_loading(True)
        self._run_member_action("set_role", user_id=str(member.get("user_id") or ""), role=role)

    def _start_remove_member(self, member: dict[str, Any]) -> None:
        if not self._can_remove_member(member):
            return
        self._run_member_action("remove", user_id=str(member.get("user_id") or ""))

    def _on_member_action_success(self, message: str) -> None:
        if self._members_drawer is not None:
            self._members_drawer.set_add_member_loading(False)
            self._members_drawer.show_members_view()
        if self._set_role_dialog is not None:
            self._set_role_dialog.set_loading(False)
            self._set_role_dialog.accept()
            self._set_role_dialog = None
        self.top_bar.set_subtitle(message)
        self.reload_room_data()

    def _on_member_action_failed(self, message: str) -> None:
        if self._members_drawer is not None:
            self._members_drawer.set_add_member_loading(False)
            self._members_drawer.show_error(message)
        if self._set_role_dialog is not None:
            self._set_role_dialog.set_loading(False)
            self._set_role_dialog.error_label.show_error(message)
        self.error_toast.show_error(message)

    def _open_versions_dialog(self, file_data: dict[str, Any]) -> None:
        if self._versions_thread and self._versions_thread.isRunning():
            return
        if self._versions_dialog is None:
            self._versions_dialog = FileVersionsDialog(self)
        self._versions_dialog.set_versions(file_data.get("name", "Selected File"), [])
        self._versions_dialog.show()
        self._versions_dialog.raise_()
        self._versions_dialog.activateWindow()

        self._versions_thread = QThread(self)
        self._versions_worker = FileVersionsWorker(
            self._runtime,
            self._token,
            self.room_id,
            str(file_data.get("original_name") or file_data.get("name") or ""),
        )
        self._versions_worker.moveToThread(self._versions_thread)
        self._versions_thread.started.connect(self._versions_worker.run)
        self._versions_worker.success.connect(lambda versions: self._on_versions_loaded(file_data, versions))
        self._versions_worker.failure.connect(self._on_versions_failed)
        self._versions_worker.success.connect(self._versions_thread.quit)
        self._versions_worker.failure.connect(self._versions_thread.quit)
        self._versions_thread.finished.connect(self._versions_thread.deleteLater)
        self._versions_thread.finished.connect(self._versions_worker.deleteLater)
        self._versions_thread.finished.connect(self._cleanup_versions_thread)
        self._versions_thread.start()

    def _on_versions_loaded(self, file_data: dict[str, Any], versions: list[dict[str, Any]]) -> None:
        if self._versions_dialog is not None:
            self._versions_dialog.set_versions(file_data.get("name", "Selected File"), versions)

    def _on_versions_failed(self, message: str) -> None:
        if self._versions_dialog is not None:
            self._versions_dialog.error_label.show_error(message)

    def _confirm_delete_file(self, file_data: dict[str, Any]) -> None:
        if not self._can_delete_file_item(file_data):
            self.error_toast.show_error("You do not have permission to delete this file.")
            return
        self._show_delete_confirm_panel(file_data)

    def _start_delete_worker(self, file_data: dict[str, Any]) -> None:
        if self._delete_thread and self._delete_thread.isRunning():
            return

        self._delete_thread = QThread(self)
        self._delete_worker = FileDeleteWorker(self._runtime, self._token, str(file_data.get("file_id") or ""))
        self._delete_worker.moveToThread(self._delete_thread)
        self._delete_thread.started.connect(self._delete_worker.run)
        self._delete_worker.success.connect(self._on_delete_success)
        self._delete_worker.failure.connect(self._on_delete_failed)
        self._delete_worker.success.connect(self._delete_thread.quit)
        self._delete_worker.failure.connect(self._delete_thread.quit)
        self._delete_thread.finished.connect(self._delete_thread.deleteLater)
        self._delete_thread.finished.connect(self._delete_worker.deleteLater)
        self._delete_thread.finished.connect(self._cleanup_delete_thread)
        self._delete_thread.start()

    def _on_delete_success(self, message: str) -> None:
        self._hide_delete_confirm_panel()
        self._selected_file = {}
        self._update_file_detail({})
        self.top_bar.set_subtitle(message)
        self.reload_room_data()

    def _on_delete_failed(self, message: str) -> None:
        self._hide_delete_confirm_panel()
        self.error_toast.show_error(message)

    def _open_upload_dialog(self) -> None:
        if not self._can_upload_files():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose file to upload")
        if not file_path:
            return
        if self._upload_thread and self._upload_thread.isRunning():
            return

        self._upload_thread = QThread(self)
        self._upload_worker = FileUploadWorker(
            self._runtime,
            self._token,
            self.room_id,
            file_path,
            self._current_user_id or self._current_username or self._username,
        )
        self._pending_uploaded_file_name = Path(file_path).name
        self._upload_worker.moveToThread(self._upload_thread)
        self._upload_thread.started.connect(self._upload_worker.run)
        self._upload_worker.success.connect(self._on_upload_success)
        self._upload_worker.failure.connect(self._on_upload_failed)
        self._upload_worker.success.connect(self._upload_thread.quit)
        self._upload_worker.failure.connect(self._upload_thread.quit)
        self._upload_thread.finished.connect(self._upload_thread.deleteLater)
        self._upload_thread.finished.connect(self._upload_worker.deleteLater)
        self._upload_thread.finished.connect(self._cleanup_upload_thread)
        self._upload_thread.start()
        self.top_bar.set_subtitle("Uploading file to secure storage...")

    def _on_upload_success(self, message: str) -> None:
        self.top_bar.set_subtitle(message)
        self.reload_room_data()

    def _on_upload_failed(self, message: str) -> None:
        self._pending_uploaded_file_name = ""
        self.error_toast.show_error(message)

    def _start_download(self, file_data: dict[str, Any]) -> None:
        default_name = str(file_data.get("name") or "download.bin")
        save_path, _ = QFileDialog.getSaveFileName(self, "Save file", default_name)
        if not save_path:
            return
        if self._download_thread and self._download_thread.isRunning():
            return

        self._download_thread = QThread(self)
        self._download_worker = FileDownloadWorker(
            self._runtime,
            self._token,
            str(file_data.get("file_id") or ""),
            default_name,
            int(file_data.get("version") or 1),
            self._current_user_id or self._current_username or self._username,
            save_path,
        )
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.success.connect(self._on_download_success)
        self._download_worker.failure.connect(self._on_download_failed)
        self._download_worker.success.connect(self._download_thread.quit)
        self._download_worker.failure.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._download_thread.deleteLater)
        self._download_thread.finished.connect(self._download_worker.deleteLater)
        self._download_thread.finished.connect(self._cleanup_download_thread)
        self._download_thread.start()
        self.top_bar.set_subtitle("Preparing secure download...")

    def _on_download_success(self, message: str) -> None:
        self.top_bar.set_subtitle(message)

    def _on_download_failed(self, message: str) -> None:
        self.error_toast.show_error(message)

    def _cleanup_data_thread(self) -> None:
        self._data_thread = None
        self._data_worker = None

    def _cleanup_detail_thread(self) -> None:
        self._detail_thread = None
        self._detail_worker = None

    def _cleanup_member_thread(self) -> None:
        self._member_thread = None
        self._member_worker = None

    def _cleanup_versions_thread(self) -> None:
        self._versions_thread = None
        self._versions_worker = None

    def _cleanup_delete_thread(self) -> None:
        self._delete_thread = None
        self._delete_worker = None

    def _cleanup_upload_thread(self) -> None:
        self._upload_thread = None
        self._upload_worker = None

    def _cleanup_download_thread(self) -> None:
        self._download_thread = None
        self._download_worker = None

    def closeEvent(self, event) -> None:  # noqa: N802
        for thread_name in (
            "_data_thread",
            "_detail_thread",
            "_member_thread",
            "_versions_thread",
            "_delete_thread",
            "_upload_thread",
            "_download_thread",
        ):
            thread = getattr(self, thread_name, None)
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(2000)
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    load_app_fonts()
    app.setFont(app_font(10))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(PALETTE.background))
    app.setPalette(palette)

    demo_room = {
        "room_id": "demo-room-id",
        "room_name": "Project Alpha",
        "role": "OWNER",
        "current_user_id": "demo-user-id",
        "current_username": "admin",
    }
    page = RoomPage(demo_room, "admin", "demo-user-id", "admin@example.com", "", "ADMIN", DashboardRuntimeConfig())
    page.resize(1360, 840)
    page.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


__all__ = ["RoomPage"]
