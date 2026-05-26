"""Deduplication checker for file uploads."""
from typing import Optional, Dict, Any
from database import Database
from logging_config import get_logger

logger = get_logger(__name__)


class DeduplicationChecker:
    """Checks for existing files with matching content hash."""
    
    def __init__(self, database: Database):
        """
        Initialize deduplication checker.
        
        Args:
            database: Database instance
        """
        self.db = database
    
    def check_deduplication(
        self,
        sha256_whole: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a file with matching SHA256 hash already exists.
        
        Queries files table for existing file with:
        - matching sha256_whole
        - status = 'READY'
        
        Args:
            sha256_whole: SHA256 hash of file content
        
        Returns:
            File record dictionary if found, None otherwise
            Dictionary contains: id, stored_name, room_id, original_name
        """
        try:
            # Query for existing file with matching hash and READY status
            files = self.db.execute_query(
                """
                SELECT id, stored_name, room_id, original_name, size_bytes, storage_node_id
                FROM files
                WHERE sha256_whole = %s AND status = %s
                LIMIT 1
                """,
                (sha256_whole, 'READY')
            )
            
            if files:
                file = files[0]
                logger.info(
                    f"Deduplication match found: hash={sha256_whole[:16]}..., "
                    f"stored_name={file['stored_name']}"
                )
                return {
                    'id': file['id'],
                    'stored_name': file['stored_name'],
                    'room_id': file['room_id'],
                    'original_name': file['original_name'],
                    'size_bytes': file['size_bytes'],
                    'sha256_whole': sha256_whole,
                    'storage_node_id': file.get('storage_node_id')
                }
            
            logger.debug(f"No deduplication match for hash {sha256_whole[:16]}...")
            return None
            
        except Exception as e:
            logger.error(f"Failed to check deduplication: {e}")
            # Return None on error to proceed with normal upload
            return None

    def find_deduplication_candidates(
        self,
        sha256_whole: str
    ) -> list[Dict[str, Any]]:
        """
        Return READY files with matching content hash.

        Upload load-balancing uses this to prefer a duplicate that already lives
        on a healthy storage node.
        """
        try:
            files = self.db.execute_query(
                """
                SELECT id, stored_name, room_id, original_name, size_bytes, storage_node_id
                FROM files
                WHERE sha256_whole = %s AND status = %s
                ORDER BY created_at ASC
                LIMIT 20
                """,
                (sha256_whole, 'READY')
            )

            return [
                {
                    'id': file['id'],
                    'stored_name': file['stored_name'],
                    'room_id': file['room_id'],
                    'original_name': file['original_name'],
                    'size_bytes': file['size_bytes'],
                    'sha256_whole': sha256_whole,
                    'storage_node_id': file.get('storage_node_id')
                }
                for file in files
            ]
        except Exception as e:
            logger.error(f"Failed to list deduplication candidates: {e}")
            return []

    def find_same_room_duplicate(
        self,
        room_id: str,
        sha256_whole: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find a file in the same room with identical content hash.

        READY files are visible duplicates; UPLOADING files are treated as
        duplicates too so concurrent uploads of the same content are rejected.
        """
        try:
            files = self.db.execute_query(
                """
                SELECT id, room_id, original_name, status, stored_name, size_bytes, storage_node_id
                FROM files
                WHERE room_id = %s
                  AND sha256_whole = %s
                  AND status IN ('READY', 'UPLOADING')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (room_id, sha256_whole)
            )
            if not files:
                return None

            file = files[0]
            return {
                'id': file['id'],
                'room_id': file['room_id'],
                'original_name': file['original_name'],
                'status': file['status'],
                'stored_name': file.get('stored_name'),
                'size_bytes': file.get('size_bytes'),
                'storage_node_id': file.get('storage_node_id')
            }
        except Exception as e:
            logger.error(f"Failed to detect same-room duplicate: {e}")
            return None
