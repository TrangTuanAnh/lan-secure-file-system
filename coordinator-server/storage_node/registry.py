"""In-memory registry and load balancer for connected Storage Nodes."""
import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Any, List


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

            node_info.node_id = node_id
            node_info.data_host = data_host
            node_info.data_port = data_port
            node_info.storage_address = storage_address or self._format_address(data_host, data_port)
            node_info.authenticated = True
            node_info.update_ping_time()
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
