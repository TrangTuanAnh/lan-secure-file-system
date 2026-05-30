"""In-memory registry and load balancer for connected Storage Nodes."""
import random
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List, Iterable, Set

from logging_config import get_logger

logger = get_logger(__name__)


def _normalize(sha: Optional[str]) -> Optional[str]:
    if not sha:
        return None
    return sha.strip().lower()


@dataclass
class _Reservation:
    """A short-TTL upload slot held against a storage node.

    A reservation is created atomically with node selection (so the load
    balancer sees the slot the instant it's chosen) and released either when
    the upload finishes/fails, or when the TTL expires — whichever comes
    first. The TTL keeps the load counter honest if a client gets a plan and
    then disappears: without it, the slot would stay claimed until the
    35-minute cleanup window ran.
    """

    id: str
    node_id: str
    expires_at: float


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
    # Free disk space in bytes as reported by the storage node. None means
    # "not reported yet" — older storage nodes that don't include freeBytes
    # in their heartbeat stay selectable but get a neutral score so they
    # aren't unfairly penalized.
    free_bytes: Optional[int] = None

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
            "freeBytes": self.free_bytes,
        }


class StorageNodeRegistry:
    """Tracks node health and selects upload targets."""

    def __init__(self, timeout_seconds: int = 90, min_free_bytes: int = 0):
        self.timeout_seconds = timeout_seconds
        # Nodes with reported free_bytes below this threshold are excluded
        # from upload selection. Default 0 keeps every reporting node
        # eligible — operators raise it to keep a safety margin (e.g.
        # 1 GiB) so a node never gets the "last straw" upload that fills it.
        self.min_free_bytes = min_free_bytes
        self._nodes_by_connection: Dict[Any, StorageNodeInfo] = {}
        self._nodes_by_id: Dict[str, StorageNodeInfo] = {}
        self._reservations: Dict[str, _Reservation] = {}
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

    def heartbeat(
        self,
        connection: Any,
        free_bytes: Optional[int] = None,
    ) -> Optional[StorageNodeInfo]:
        """Refresh last-ping timestamp for a node and optionally update freeBytes.

        ``free_bytes=None`` preserves the previously-known capacity so a PING
        that skips the field doesn't reset the load-balancer's view.
        """
        with self._lock:
            node_info = self._nodes_by_connection.get(connection)
            if node_info:
                node_info.update_ping_time()
                if free_bytes is not None:
                    node_info.free_bytes = free_bytes
            return node_info

    def update_capacity(self, connection: Any, free_bytes: int) -> Optional[StorageNodeInfo]:
        """Record the latest free-disk-space reading from a storage node.

        Called by the storage-node server handler when a PING or
        STORAGE_AUTH payload includes `freeBytes`. Callers that don't have
        a connection (e.g. tests, admin tooling) should use the heartbeat
        path or set free_bytes on the node_info directly.
        """
        if free_bytes is None or free_bytes < 0:
            return None
        with self._lock:
            node_info = self._nodes_by_connection.get(connection)
            if node_info:
                node_info.free_bytes = free_bytes
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

    def select_for_upload(
        self,
        reservation_id: Optional[str] = None,
        ttl_seconds: int = 60,
    ) -> Optional[StorageNodeInfo]:
        """Pick a healthy node for an upload and (optionally) reserve a slot.

        Selection uses the **Power of Two Choices** algorithm: pick two
        random healthy nodes and return the one with fewer active uploads.
        With one healthy node, that node is returned directly. P2C avoids
        the "herd" failure mode of pure least-loaded — when several
        coordinators all see the same node as least-loaded at the same
        instant, they don't all pile onto it.

        When ``reservation_id`` is given, the selection is paired with an
        atomic slot reservation: the node's ``active_uploads`` counter is
        incremented and an entry is recorded with a TTL. The pair is atomic
        because both happen under the same lock acquisition, so a concurrent
        ``select_for_upload`` immediately observes the updated load.
        """
        with self._lock:
            # Self-healing: reservations that nobody released are reclaimed
            # here. Lazy-reap on every select keeps the load view fresh
            # without a dedicated background thread.
            self._reap_expired_locked()

            healthy = [
                node
                for node in self._nodes_by_id.values()
                if node.is_healthy(self.timeout_seconds)
                and node.storage_address
                and self._has_enough_capacity(node)
            ]
            if not healthy:
                return None

            if len(healthy) == 1:
                pick = healthy[0]
            else:
                two = random.sample(healthy, 2)
                pick = min(two, key=self._upload_score)

            if reservation_id:
                # Replace any prior reservation under the same id (retry
                # path) so we don't double-count the same upload.
                existing = self._reservations.get(reservation_id)
                if existing:
                    self._release_reservation_locked(existing)
                self._reservations[reservation_id] = _Reservation(
                    id=reservation_id,
                    node_id=pick.node_id,
                    expires_at=time.time() + ttl_seconds,
                )
                pick.active_uploads += 1

            return pick

    def release_reservation(self, reservation_id: Optional[str]) -> bool:
        """Release a slot held by reservation_id. Idempotent.

        Safe to call multiple times — if the reservation already expired or
        was never created, this is a no-op returning False.
        """
        if not reservation_id:
            return False
        with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if not reservation:
                return False
            self._release_reservation_locked(reservation, pop=False)
            return True

    def _release_reservation_locked(self, reservation: _Reservation, pop: bool = True) -> None:
        """Decrement the node's counter for one reservation. Caller holds lock."""
        if pop:
            self._reservations.pop(reservation.id, None)
        node = self._nodes_by_id.get(reservation.node_id)
        if node and node.active_uploads > 0:
            node.active_uploads -= 1

    def _has_enough_capacity(self, node: StorageNodeInfo) -> bool:
        """Filter rule: a node is eligible for new uploads unless it has
        explicitly reported free_bytes below the configured threshold.

        Unknown free_bytes (None) means the node hasn't reported capacity
        yet — kept eligible for backward compat with storage nodes that
        don't include freeBytes in heartbeats.
        """
        if self.min_free_bytes <= 0:
            return True
        if node.free_bytes is None:
            return True
        return node.free_bytes >= self.min_free_bytes

    @staticmethod
    def _upload_score(node: StorageNodeInfo) -> tuple:
        """Order key used by the P2C comparator. Smaller is better.

        Primary: active_uploads (least-loaded wins).
        Tie-breaker: more free_bytes wins, so when two nodes have the same
        in-flight count we steer the upload toward the node with more room.
        ``None`` is treated as "infinite" capacity so unreported nodes
        aren't punished; alphabetic node_id resolves the final tie.
        """
        free_for_sort = node.free_bytes if node.free_bytes is not None else float("inf")
        return (node.active_uploads, -free_for_sort, node.node_id)

    def _reap_expired_locked(self) -> int:
        """Drop reservations past their TTL. Caller holds lock."""
        now = time.time()
        expired = [r for r in self._reservations.values() if r.expires_at <= now]
        for reservation in expired:
            self._release_reservation_locked(reservation)
            logger.info(
                f"Upload slot reservation {reservation.id} on node "
                f"{reservation.node_id} expired; counter released"
            )
        return len(expired)

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
