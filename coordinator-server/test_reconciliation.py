"""Tests for storage_node.reconciliation_service.ReconciliationService."""
from typing import List, Tuple

from storage_node.reconciliation_service import ReconciliationService


class FakeDB:
    """In-memory stand-in for Database used by ReconciliationService."""

    def __init__(self, rows: List[dict]):
        # Each row: {'id': str, 'sha256_whole': str, 'status': str, 'storage_node_id': str}
        self._rows = rows
        self.updates: List[Tuple[str, str]] = []  # (file_id, new_status)

    def execute_query(self, sql: str, params=None):
        # We only handle the one query reconcile_node issues.
        node_id = params[0]
        return [
            {
                'id': row['id'],
                'sha256_whole': row['sha256_whole'],
                'original_name': row.get('original_name', 'f'),
            }
            for row in self._rows
            if row['storage_node_id'] == node_id and row['status'] == 'READY'
        ]

    def execute_update(self, sql: str, params=None):
        # Only the MISSING UPDATE is expected.
        new_status, file_id = params
        self.updates.append((file_id, new_status))
        for row in self._rows:
            if row['id'] == file_id and row['status'] == 'READY':
                row['status'] = new_status


def test_marks_missing_files_as_missing():
    db = FakeDB([
        {'id': 'f1', 'sha256_whole': 'AAA', 'status': 'READY', 'storage_node_id': 'node-1'},
        {'id': 'f2', 'sha256_whole': 'BBB', 'status': 'READY', 'storage_node_id': 'node-1'},
        {'id': 'f3', 'sha256_whole': 'CCC', 'status': 'READY', 'storage_node_id': 'node-1'},
    ])
    svc = ReconciliationService(db)

    # Node only reports AAA → BBB and CCC are gone.
    missing = svc.reconcile_node('node-1', ['aaa'])

    assert sorted(missing) == ['f2', 'f3']
    assert (db.updates.count(('f2', 'MISSING')) == 1)
    assert (db.updates.count(('f3', 'MISSING')) == 1)


def test_no_updates_when_manifest_matches():
    db = FakeDB([
        {'id': 'f1', 'sha256_whole': 'aaa', 'status': 'READY', 'storage_node_id': 'node-1'},
    ])
    svc = ReconciliationService(db)

    missing = svc.reconcile_node('node-1', ['AAA'])

    assert missing == []
    assert db.updates == []


def test_only_touches_files_owned_by_this_node():
    db = FakeDB([
        {'id': 'f1', 'sha256_whole': 'AAA', 'status': 'READY', 'storage_node_id': 'node-1'},
        {'id': 'f2', 'sha256_whole': 'BBB', 'status': 'READY', 'storage_node_id': 'node-2'},
    ])
    svc = ReconciliationService(db)

    # node-1 reports nothing — but we should not touch node-2's file.
    svc.reconcile_node('node-1', [])

    assert ('f1', 'MISSING') in db.updates
    assert all(fid != 'f2' for fid, _ in db.updates)


def test_ignores_non_ready_files():
    db = FakeDB([
        {'id': 'f1', 'sha256_whole': 'AAA', 'status': 'UPLOADING', 'storage_node_id': 'node-1'},
        {'id': 'f2', 'sha256_whole': 'BBB', 'status': 'DELETED', 'storage_node_id': 'node-1'},
    ])
    svc = ReconciliationService(db)

    missing = svc.reconcile_node('node-1', [])

    assert missing == []
    assert db.updates == []


def test_empty_node_id_returns_empty():
    db = FakeDB([])
    svc = ReconciliationService(db)
    assert svc.reconcile_node('', ['AAA']) == []
