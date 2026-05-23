"""Reconcile DB file assignments against a storage node's reported manifest."""
from typing import Iterable, List, Set

from database import Database
from logging_config import get_logger

logger = get_logger(__name__)


class ReconciliationService:
    """
    Compare what the DB says a node holds against what the node reports.

    When a file is assigned to node X in DB with status READY but the node's
    manifest does not contain its sha256, the file is considered lost on
    that node and is marked MISSING.
    """

    def __init__(self, database: Database):
        self.db = database

    def reconcile_node(
        self,
        node_id: str,
        manifest_sha_set: Iterable[str],
    ) -> List[str]:
        """
        Mark files as MISSING when the node no longer reports their sha256.

        Returns the list of file IDs marked MISSING.
        """
        if not node_id:
            return []

        normalized: Set[str] = {
            sha.strip().lower()
            for sha in manifest_sha_set
            if sha
        }

        try:
            rows = self.db.execute_query(
                """
                SELECT id, sha256_whole, original_name
                FROM files
                WHERE storage_node_id = %s AND status = 'READY'
                """,
                (node_id,)
            )
        except Exception as e:
            logger.error(f"Reconciliation query failed for node {node_id}: {e}")
            return []

        missing_ids: List[str] = []
        for row in rows:
            sha = (row.get('sha256_whole') or '').strip().lower()
            if sha and sha not in normalized:
                missing_ids.append(str(row['id']))

        for file_id in missing_ids:
            try:
                self.db.execute_update(
                    "UPDATE files SET status = %s WHERE id = %s AND status = 'READY'",
                    ('MISSING', file_id)
                )
            except Exception as e:
                logger.error(f"Failed to mark file {file_id} MISSING: {e}")

        if missing_ids:
            logger.warning(
                f"Reconciliation marked {len(missing_ids)} file(s) MISSING on node {node_id}: "
                f"{missing_ids[:10]}{'...' if len(missing_ids) > 10 else ''}"
            )
        else:
            logger.info(
                f"Reconciliation OK on node {node_id}: "
                f"{len(rows)} READY file(s), {len(normalized)} in manifest"
            )

        return missing_ids
