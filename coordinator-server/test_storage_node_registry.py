"""Tests for Storage Node registry load-balancing."""
import time
from unittest.mock import patch

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


# ── Power-of-Two-Choices + slot reservation TTL ─────────────────────────────

def test_p2c_uses_random_sample_when_multiple_healthy_nodes():
    """With ≥2 nodes, selection must use random.sample (P2C), not pure
    least-loaded sort. We verify by mocking random.sample and asserting it
    was called with the healthy candidate set."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-a", 9001)
    authenticate(registry, "node-b", 9002)
    authenticate(registry, "node-c", 9003)

    with patch("storage_node.registry.random.sample") as mock_sample:
        # Return a fixed pair so we can assert it was actually used.
        nodes_view = [registry.get_node(n) for n in ("node-a", "node-b", "node-c")]
        mock_sample.return_value = [nodes_view[1], nodes_view[2]]  # b, c

        selected = registry.select_for_upload()

        assert mock_sample.called, "P2C should call random.sample"
        # Of the (b, c) pair, both have 0 uploads; min by node_id picks b.
        assert selected.node_id == "node-b"


def test_p2c_skipped_with_single_healthy_node():
    """With only one healthy node, no random pick needed."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-only", 9001)

    with patch("storage_node.registry.random.sample") as mock_sample:
        selected = registry.select_for_upload()

    assert not mock_sample.called
    assert selected.node_id == "node-only"


def test_select_with_reservation_id_increments_counter_atomically():
    registry = StorageNodeRegistry(timeout_seconds=90)
    node = authenticate(registry, "node-1", 9001)
    assert node.active_uploads == 0

    selected = registry.select_for_upload(reservation_id="file-abc", ttl_seconds=60)

    assert selected.node_id == "node-1"
    # The reservation bumped the counter as part of the same lock acquisition.
    assert node.active_uploads == 1
    assert "file-abc" in registry._reservations


def test_release_reservation_decrements_counter():
    registry = StorageNodeRegistry(timeout_seconds=90)
    node = authenticate(registry, "node-1", 9001)
    registry.select_for_upload(reservation_id="file-abc", ttl_seconds=60)
    assert node.active_uploads == 1

    released = registry.release_reservation("file-abc")

    assert released is True
    assert node.active_uploads == 0
    assert "file-abc" not in registry._reservations


def test_release_reservation_is_idempotent():
    registry = StorageNodeRegistry(timeout_seconds=90)
    authenticate(registry, "node-1", 9001)
    registry.select_for_upload(reservation_id="file-abc", ttl_seconds=60)

    assert registry.release_reservation("file-abc") is True
    # Second release on an already-released id must be a no-op, not an error.
    assert registry.release_reservation("file-abc") is False


def test_expired_reservation_is_reaped_on_next_select():
    """A reservation that nobody released must be reclaimed when its TTL
    elapses. We trigger the reap by issuing a subsequent select_for_upload."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    node_a = authenticate(registry, "node-a", 9001)

    # Reserve with TTL=0 → expired the instant it is created.
    registry.select_for_upload(reservation_id="orphan", ttl_seconds=0)
    assert node_a.active_uploads == 1
    # A subsequent select reaps expired reservations before scoring.
    registry.select_for_upload()
    assert node_a.active_uploads == 0
    assert "orphan" not in registry._reservations


def test_no_healthy_node_does_not_create_reservation():
    registry = StorageNodeRegistry(timeout_seconds=1)
    stale = authenticate(registry, "node-1", 9001)
    stale.last_ping_time = time.time() - 10

    selected = registry.select_for_upload(reservation_id="file-x", ttl_seconds=60)

    assert selected is None
    assert "file-x" not in registry._reservations


# ── Weighted P2C by free_bytes ──────────────────────────────────────────────

def test_score_tiebreaks_in_favor_of_more_free_bytes():
    """Two nodes with the same active_uploads: the one with more free disk
    space wins, because that's where the next upload is least likely to
    push capacity over the edge."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    full_ish = authenticate(registry, "node-tight", 9001)
    spacious = authenticate(registry, "node-roomy", 9002)
    full_ish.free_bytes = 1 * 1024 * 1024 * 1024        # 1 GiB
    spacious.free_bytes = 50 * 1024 * 1024 * 1024       # 50 GiB

    # Force P2C to compare exactly these two so the result is deterministic.
    with patch("storage_node.registry.random.sample") as mock_sample:
        mock_sample.return_value = [full_ish, spacious]
        selected = registry.select_for_upload()

    assert selected.node_id == "node-roomy"


def test_load_dominates_free_space():
    """active_uploads is the primary criterion: a busy roomy node still
    loses to a quiet tight node. Free space is only a tiebreaker."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    quiet_tight = authenticate(registry, "node-quiet", 9001)
    busy_roomy = authenticate(registry, "node-busy", 9002)
    quiet_tight.active_uploads = 0
    quiet_tight.free_bytes = 2 * 1024 * 1024 * 1024     # 2 GiB
    busy_roomy.active_uploads = 5
    busy_roomy.free_bytes = 500 * 1024 * 1024 * 1024    # 500 GiB

    with patch("storage_node.registry.random.sample") as mock_sample:
        mock_sample.return_value = [quiet_tight, busy_roomy]
        selected = registry.select_for_upload()

    assert selected.node_id == "node-quiet"


def test_min_free_bytes_filters_out_tight_nodes():
    """A node below the min_free_bytes threshold is excluded entirely —
    not even eligible for the random sample. This is how operators set a
    safety floor so the load balancer stops piling onto a near-full node."""
    registry = StorageNodeRegistry(
        timeout_seconds=90,
        min_free_bytes=10 * 1024 * 1024 * 1024,  # require ≥10 GiB free
    )
    tight = authenticate(registry, "node-tight", 9001)
    roomy = authenticate(registry, "node-roomy", 9002)
    tight.free_bytes = 1 * 1024 * 1024 * 1024            # under threshold
    roomy.free_bytes = 100 * 1024 * 1024 * 1024          # over threshold

    selected = registry.select_for_upload()

    assert selected.node_id == "node-roomy"


def test_min_free_bytes_returns_none_when_all_too_tight():
    registry = StorageNodeRegistry(
        timeout_seconds=90,
        min_free_bytes=10 * 1024 * 1024 * 1024,
    )
    a = authenticate(registry, "node-a", 9001)
    b = authenticate(registry, "node-b", 9002)
    a.free_bytes = 1 * 1024 * 1024
    b.free_bytes = 2 * 1024 * 1024

    assert registry.select_for_upload() is None


def test_unknown_free_bytes_is_neutral_for_legacy_storage_nodes():
    """Storage nodes that never report freeBytes (older Java code) must
    still be selectable — free_bytes=None is treated as infinite capacity
    so they aren't unfairly penalized against reporting peers."""
    registry = StorageNodeRegistry(timeout_seconds=90)
    legacy = authenticate(registry, "node-legacy", 9001)
    reporter = authenticate(registry, "node-reporter", 9002)
    # legacy.free_bytes stays None
    reporter.free_bytes = 100 * 1024 * 1024 * 1024

    # With None treated as inf, both look "infinite" — but the legacy node
    # comes out ahead because it sorts equal and node-legacy < node-reporter.
    with patch("storage_node.registry.random.sample") as mock_sample:
        mock_sample.return_value = [legacy, reporter]
        selected = registry.select_for_upload()

    assert selected is not None
    # Either is acceptable in principle, but specifically: legacy wins on
    # alphabetic tiebreak — proving it wasn't excluded for unknown capacity.
    assert selected.node_id == "node-legacy"


def test_heartbeat_records_free_bytes():
    registry = StorageNodeRegistry(timeout_seconds=90)
    node = authenticate(registry, "node-1", 9001)
    assert node.free_bytes is None

    registry.heartbeat(node.connection, free_bytes=42 * 1024 * 1024 * 1024)

    assert node.free_bytes == 42 * 1024 * 1024 * 1024


def test_update_capacity_ignores_negative_or_none():
    registry = StorageNodeRegistry(timeout_seconds=90)
    node = authenticate(registry, "node-1", 9001)
    node.free_bytes = 100

    # Negative or None are rejected silently to keep one bad reading from
    # corrupting load-balancer state.
    registry.update_capacity(node.connection, -1)
    assert node.free_bytes == 100
    registry.update_capacity(node.connection, None)  # type: ignore[arg-type]
    assert node.free_bytes == 100

    registry.update_capacity(node.connection, 200)
    assert node.free_bytes == 200
