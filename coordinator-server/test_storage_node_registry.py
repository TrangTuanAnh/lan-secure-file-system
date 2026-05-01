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
