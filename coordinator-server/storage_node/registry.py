"""In-memory registry and load balancer for connected Storage Nodes."""
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List, Iterable, Set


def _normalize(sha: Optional[str]) -> Optional[str]:
    if not sha:
        return None
    return sha.strip().lower()


@dataclass
class StorageNodeInfo:
    """Information about a connected Storage Node."""

    connection: Any
    node_id: str
    data_host: Optional[str] = None
    data_port: Optional[int] = None
    storage_address: Optional[str] = None
    authenticated: bool = False
    active_uploads: int = 0
    files: Set[str] = field(default_factory=set)
    manifest_received: bool = False

    def __post_init__(self) -> None:
        self.last_ping_time = time.time()
        self.connected_at = time.time()

    def update_ping_time(self) -> None:
        self.last_ping_time = time.time()

    def is_healthy(self, timeout_seconds: int) -> bool:
        return self.authenticated and (time.time() - self.last_ping_time) < timeout_seconds

    def to_dict(self, timeout_seconds: int) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "nodeId": self.node_id,
            "authenticated": self.authenticated,
            "connected_at": self.connected_at,
            "last_ping_time": self.last_ping_time,
            "healthy": self.is_healthy(timeout_seconds),
            "dataHost": self.data_host,
            "dataPort": self.data_port,
            "storageAddress": self.storage_address,
            "activeUploads": self.active_uploads,
            "manifestReceived": self.manifest_received,
            "fileCount": len(self.files),
        }


class StorageNodeRegistry:
    """Tracks node health and selects upload targets."""

    def __init__(self, timeout_seconds: int = 90):
        self.timeout_seconds = timeout_seconds
        self._nodes_by_connection: Dict[Any, StorageNodeInfo] = {}
        self._nodes_by_id: Dict[str, StorageNodeInfo] = {}
        self._lock = threading.Lock()

    def add_connection(self, connection: Any) -> StorageNodeInfo:
        with self._lock:
            node_info = StorageNodeInfo(connection=connection, node_id=connection.connection_id)
            self._nodes_by_connection[connection] = node_info
            return node_info

    def authenticate(
        self,
        connection: Any,
        node_id: str,
        data_host: Optional[str],
        data_port: Optional[int],
        storage_address: Optional[str],
    ) -> StorageNodeInfo:
        with self._lock:
            node_info = self._nodes_by_connection.get(connection)
            if node_info is None:
                node_info = StorageNodeInfo(connection=connection, node_id=node_id)
                self._nodes_by_connection[connection] = node_info

            old_node = self._nodes_by_id.get(node_id)
            if old_node and old_node.connection is not connection:
                self._nodes_by_connection.pop(old_node.connection, None)
                # BUGFIX M7: close the orphaned old socket so it doesn't leak
                # file descriptors and doesn't keep receiving events from
                # the now-replaced connection.
                try:
                    old_node.connection.close()
                except Exception:
                    pass

            node_info.node_id = node_id
            node_info.data_host = data_host
            node_info.data_port = data_port
            node_info.storage_address = storage_address or self._format_address(data_host, data_port)
            node_info.authenticated = True
            node_info.update_ping_time()
            # Fresh auth = stale manifest. Wait for a new full one before trusting.
            node_info.files = set()
            node_info.manifest_received = False
            self._nodes_by_id[node_id] = node_info
            return node_info

    def remove_connection(self, connection: Any) -> Optional[StorageNodeInfo]:
        with self._lock:
            node_info = self._nodes_by_connection.pop(connection, None)
            if node_info and self._nodes_by_id.get(node_info.node_id) is node_info:
                self._nodes_by_id.pop(node_info.node_id, None)
            return node_info

    def heartbeat(self, connection: Any) -> Optional[StorageNodeInfo]:
        with self._lock:
            node_info = self._nodes_by_connection.get(connection)
            if node_info:
                node_info.update_ping_time()
            return node_info

    def get_by_connection(self, connection: Any) -> Optional[StorageNodeInfo]:
        with self._lock:
            return self._nodes_by_connection.get(connection)

    def get_node(self, node_id: Optional[str]) -> Optional[StorageNodeInfo]:
        if not node_id:
            return None
        with self._lock:
            return self._nodes_by_id.get(node_id)

    def is_node_healthy(self, node_id: Optional[str]) -> bool:
        node_info = self.get_node(node_id)
        return bool(node_info and node_info.is_healthy(self.timeout_seconds))

    def get_storage_address(self, node_id: Optional[str]) -> Optional[str]:
        node_info = self.get_node(node_id)
        if node_info and node_info.is_healthy(self.timeout_seconds):
            return node_info.storage_address
        return None

    def select_for_upload(self) -> Optional[StorageNodeInfo]:
        with self._lock:
            healthy = [
                node
                for node in self._nodes_by_id.values()
                if node.is_healthy(self.timeout_seconds) and node.storage_address
            ]
            if not healthy:
                return None
            healthy.sort(key=lambda node: (node.active_uploads, node.node_id))
            return healthy[0]

    def mark_upload_started(self, node_id: Optional[str]) -> None:
        self.increment_active_uploads(node_id)

    def mark_upload_finished(self, node_id: Optional[str]) -> None:
        self.decrement_active_uploads(node_id)

    def increment_active_uploads(self, node_id: Optional[str]) -> None:
        if not node_id:
            return
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if node_info:
                node_info.active_uploads += 1

    def decrement_active_uploads(self, node_id: Optional[str]) -> None:
        if not node_id:
            return
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if node_info and node_info.active_uploads > 0:
                node_info.active_uploads -= 1

    def set_manifest(self, node_id: Optional[str], file_ids: Iterable[str]) -> Optional[Set[str]]:
        """
        Replace a node's manifest with the full list and mark manifest_received=True.

        Returns the new (normalized) manifest set so the caller can run
        reconciliation, or None if the node is unknown.
        """
        if not node_id:
            return None
        normalized = {n for n in (_normalize(f) for f in file_ids) if n}
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if not node_info:
                return None
            node_info.files = normalized
            node_info.manifest_received = True
        return normalized

    def apply_manifest_delta(
        self,
        node_id: Optional[str],
        added: Iterable[str],
        removed: Iterable[str],
    ) -> bool:
        if not node_id:
            return False
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if not node_info:
                return False
            for sha in added:
                norm = _normalize(sha)
                if norm:
                    node_info.files.add(norm)
            for sha in removed:
                norm = _normalize(sha)
                if norm:
                    node_info.files.discard(norm)
            return True

    def mark_file_added(self, node_id: Optional[str], sha: Optional[str]) -> None:
        """Implicit-add for events like UPLOAD_COMPLETE that race with deltas."""
        norm = _normalize(sha)
        if not node_id or not norm:
            return
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if node_info:
                node_info.files.add(norm)

    def node_has_file(self, node_id: Optional[str], sha: Optional[str]) -> bool:
        """
        Return True if the node is healthy and the file is known to be present.

        Before the first full manifest arrives we don't know what the node holds,
        so trust the DB assignment (return True) to avoid breaking downloads
        during the brief bootstrap window.
        """
        norm = _normalize(sha)
        if not node_id or not norm:
            return False
        with self._lock:
            node_info = self._nodes_by_id.get(node_id)
            if not node_info or not node_info.is_healthy(self.timeout_seconds):
                return False
            if not node_info.manifest_received:
                return True
            return norm in node_info.files

    def get_all_nodes(self) -> List[StorageNodeInfo]:
        with self._lock:
            return list(self._nodes_by_connection.values())

    def get_connected_nodes(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                node.to_dict(self.timeout_seconds)
                for node in self._nodes_by_id.values()
                if node.authenticated
            ]

    @staticmethod
    def _format_address(data_host: Optional[str], data_port: Optional[int]) -> Optional[str]:
        if not data_host or not data_port:
            return None
        return f"{data_host}:{data_port}"
