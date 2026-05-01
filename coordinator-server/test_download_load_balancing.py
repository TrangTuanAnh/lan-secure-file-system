"""Download storage-node resolution tests."""
from unittest.mock import Mock

from download.download_service import DownloadService


class FakeNode:
    def __init__(self, node_id, storage_address, healthy=True):
        self.node_id = node_id
        self.storage_address = storage_address
        self.healthy = healthy


class FakeRegistry:
    def __init__(self, nodes):
        self.nodes = {node.node_id: node for node in nodes}

    def get_storage_address(self, node_id):
        node = self.nodes.get(node_id)
        if node and node.healthy:
            return node.storage_address
        return None


def file_row(storage_node_id="node-1"):
    return {
        'id': 'file-123',
        'room_id': 'room-123',
        'original_name': 'test.txt',
        'stored_name': 'room-123/file-123',
        'version': 1,
        'size_bytes': 1024,
        'sha256_whole': 'a' * 64,
        'total_chunks': 2,
        'chunk_size': 524288,
        'status': 'READY',
        'storage_node_id': storage_node_id
    }


def make_service(registry=None):
    db = Mock()
    redis = Mock()
    authz = Mock()
    authz.check_permission.return_value = True
    service = DownloadService(
        database=db,
        redis_client=redis,
        authorization_service=authz,
        storage_registry=registry,
        storage_address="legacy-node:9000",
        ticket_secret="test-secret"
    )
    return service, db, redis, authz


def test_download_returns_owning_node_address():
    registry = FakeRegistry([FakeNode("node-1", "node-1:9001")])
    service, db, redis, _ = make_service(registry)
    db.execute_query.return_value = [file_row("node-1")]

    success, plan, error = service.handle_init_download_direct(
        user_id="user-1",
        global_role="USER",
        file_id="file-123"
    )

    assert success is True
    assert error is None
    assert plan['storageNodeId'] == "node-1"
    assert plan['storageAddress'] == "node-1:9001"
    assert plan['ticketNodeId'] == "node-1"
    redis.set_ticket.assert_called_once()


def test_download_fails_when_owning_node_unavailable():
    registry = FakeRegistry([FakeNode("node-1", "node-1:9001", healthy=False)])
    service, db, redis, _ = make_service(registry)
    db.execute_query.return_value = [file_row("node-1")]

    success, plan, error = service.handle_init_download_direct(
        user_id="user-1",
        global_role="USER",
        file_id="file-123"
    )

    assert success is False
    assert plan is None
    assert error == "STORAGE_NODE_UNAVAILABLE"
    redis.set_ticket.assert_not_called()


def test_download_legacy_null_storage_node_id_uses_fallback_address():
    registry = FakeRegistry([FakeNode("node-1", "node-1:9001", healthy=False)])
    service, db, _, _ = make_service(registry)
    db.execute_query.return_value = [file_row(None)]

    success, plan, error = service.handle_init_download_direct(
        user_id="user-1",
        global_role="USER",
        file_id="file-123"
    )

    assert success is True
    assert error is None
    assert plan['storageNodeId'] is None
    assert plan['storageAddress'] == "legacy-node:9000"
    assert plan['ticketNodeId'] == "node-1"
