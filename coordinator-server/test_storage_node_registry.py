"""Tests for Storage Node registry load-balancing."""
import time

from storage_node.registry import StorageNodeRegistry


class DummyConnection:
    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.address = ("127.0.0.1", 10000)


def authenticate(registry: StorageNodeRegistry, node_id: str, port: int):
    conn = DummyConnection(f"conn-{node_id}")
    registry.add_connection(conn)
    return registry.authenticate(
        connection=conn,
        node_id=node_id,
        data_host=node_id,
        data_port=port,
        storage_address=f"{node_id}:{port}"
    )


def test_selects_healthy_node_with_least_active_uploads():
    registry = StorageNodeRegistry(timeout_seconds=90)
    node_1 = authenticate(registry, "node-1", 9001)
    node_2 = authenticate(registry, "node-2", 9002)
    node_1.active_uploads = 3
    node_2.active_uploads = 1

    selected = registry.select_for_upload()

    assert selected.node_id == "node-2"


def test_tie_breaks_by_node_id():
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-b", 9002)
    authenticate(registry, "node-a", 9001)

    selected = registry.select_for_upload()

    assert selected.node_id == "node-a"


def test_ignores_unhealthy_and_unauthenticated_nodes():
    registry = StorageNodeRegistry(timeout_seconds=1)
    healthy = authenticate(registry, "node-healthy", 9001)
    stale = authenticate(registry, "node-stale", 9002)
    stale.last_ping_time = time.time() - 10

    unauth_conn = DummyConnection("conn-unauth")
    registry.add_connection(unauth_conn)

    selected = registry.select_for_upload()

    assert selected.node_id == healthy.node_id


def test_returns_no_node_when_none_are_healthy():
    registry = StorageNodeRegistry(timeout_seconds=1)
    stale = authenticate(registry, "node-stale", 9001)
    stale.last_ping_time = time.time() - 10

    assert registry.select_for_upload() is None


# ── Manifest tracking ──────────────────────────────────────────────────────

def test_node_has_file_trusts_db_before_manifest():
    """During bootstrap (no full manifest yet) we trust the DB assignment."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-1", 9001)

    # Manifest never sent → assume node has the file (don't break downloads).
    assert registry.node_has_file("node-1", "abc123") is True


def test_node_has_file_after_full_manifest():
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-1", 9001)

    registry.set_manifest("node-1", ["AbC", "deadbeef"])

    assert registry.node_has_file("node-1", "abc") is True
    assert registry.node_has_file("node-1", "DEADBEEF") is True
    assert registry.node_has_file("node-1", "missing") is False


def test_manifest_delta_adds_and_removes():
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-1", 9001)
    registry.set_manifest("node-1", ["a", "b"])

    registry.apply_manifest_delta("node-1", added=["C"], removed=["a"])

    assert registry.node_has_file("node-1", "c") is True
    assert registry.node_has_file("node-1", "a") is False
    assert registry.node_has_file("node-1", "b") is True


def test_mark_file_added_works_even_without_manifest():
    """Implicit-add via UPLOAD_COMPLETE should be visible immediately."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-1", 9001)
    registry.set_manifest("node-1", [])  # empty full manifest

    registry.mark_file_added("node-1", "abc")

    assert registry.node_has_file("node-1", "abc") is True


def test_node_has_file_false_when_unhealthy():
    registry = StorageNodeRegistry(timeout_seconds=1)
    stale = authenticate(registry, "node-1", 9001)
    registry.set_manifest("node-1", ["abc"])
    stale.last_ping_time = time.time() - 10

    assert registry.node_has_file("node-1", "abc") is False


def test_reauthenticate_resets_manifest():
    """A fresh STORAGE_AUTH means the node's view may have changed."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    node = authenticate(registry, "node-1", 9001)
    registry.set_manifest("node-1", ["abc"])
    assert node.manifest_received is True

    # Same node reconnects (new connection object).
    authenticate(registry, "node-1", 9001)
    refreshed = registry.get_node("node-1")

    assert refreshed.manifest_received is False
    assert refreshed.files == set()
