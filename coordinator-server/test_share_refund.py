"""Regression tests for share-token download slot accounting.

handle_init_download_share consumes a download slot with an atomic
``download_count + 1`` BEFORE it knows the file is deliverable. If a later
step fails (file gone, not READY, owning storage node unavailable), the slot
must be REFUNDED — otherwise a single-use (max_downloads=1) link is burned
forever without delivering a byte.

These tests use in-memory fakes, so they need no PostgreSQL/Redis and run
both under pytest and standalone:

    pytest coordinator-server/test_share_refund.py
    python coordinator-server/test_share_refund.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download.download_service import DownloadService


def _norm(sql):
    return " ".join(sql.split())


class FakeDB:
    """Routes the SELECT/UPDATE shapes the share handler uses; records refunds."""

    def __init__(self, files):
        self._files = files
        self.refunds = []

    def execute_query(self, sql, params=None):
        s = _norm(sql)
        if "UPDATE share_tokens" in s and "download_count + 1" in s:
            # Atomic consume succeeded -> return one token row.
            return [{
                "id": "tok-1",
                "file_id": "f1",
                "created_by": "owner-1",
                "download_count": 1,
                "max_downloads": 1,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            }]
        if "FROM files" in s:
            return list(self._files)
        return []

    def execute_update(self, sql, params=None):
        s = _norm(sql)
        if "UPDATE share_tokens" in s and "download_count - 1" in s:
            self.refunds.append(params)
        return 1


class FakeRedis:
    def set_ticket(self, *a, **k):
        return True


class FakeRegistry:
    """Registry whose only node is unreachable -> STORAGE_NODE_UNAVAILABLE."""

    def get_storage_address(self, node_id):
        return None

    def node_has_file(self, node_id, sha):
        return True


def _ready_file():
    return {
        "id": "f1", "room_id": "r1", "original_name": "a.bin",
        "stored_name": "r1/f1", "version": 1, "size_bytes": 10,
        "sha256_whole": "h", "total_chunks": 1, "chunk_size": 524288,
        "status": "READY", "storage_node_id": "node-1",
    }


def _service(files, registry=None):
    return DownloadService(
        database=FakeDB(files),
        redis_client=FakeRedis(),
        authorization_service=object(),
        audit_service=None,
        storage_registry=registry,
    )


def test_refund_when_file_missing_after_token_validation():
    svc = _service(files=[])
    success, _, err = svc.handle_init_download_share("tok", "f1")
    assert not success and err == "FILE_NOT_FOUND"
    assert len(svc.db.refunds) == 1


def test_refund_when_file_not_ready():
    f = _ready_file()
    f["status"] = "UPLOADING"
    svc = _service(files=[f])
    success, _, err = svc.handle_init_download_share("tok", "f1")
    assert not success and err == "FILE_NOT_READY"
    assert len(svc.db.refunds) == 1


def test_refund_when_storage_node_unavailable():
    svc = _service(files=[_ready_file()], registry=FakeRegistry())
    success, _, err = svc.handle_init_download_share("tok", "f1")
    assert not success and err == "STORAGE_NODE_UNAVAILABLE"
    assert len(svc.db.refunds) == 1


def test_deliverable_download_consumes_without_refund():
    svc = _service(files=[_ready_file()])  # no registry -> legacy address, deliverable
    success, plan, err = svc.handle_init_download_share("tok", "f1")
    assert success and err is None and plan is not None
    assert len(svc.db.refunds) == 0


def _run_standalone():
    tests = [
        test_refund_when_file_missing_after_token_validation,
        test_refund_when_file_not_ready,
        test_refund_when_storage_node_unavailable,
        test_deliverable_download_consumes_without_refund,
    ]
    ok = True
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            ok = False
            print(f"FAIL {t.__name__}: {e}")
    print("=>", "ALL SHARE-REFUND ASSERTIONS PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_run_standalone())
