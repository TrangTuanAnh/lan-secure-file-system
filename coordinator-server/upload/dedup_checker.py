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
                SELECT id, stored_name, room_id, original_name, size_bytes
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
                    'size_bytes': file['size_bytes']
                }
            
            logger.debug(f"No deduplication match for hash {sha256_whole[:16]}...")
            return None
            
        except Exception as e:
            logger.error(f"Failed to check deduplication: {e}")
            # Return None on error to proceed with normal upload
            return None
