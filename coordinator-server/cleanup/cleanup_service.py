"""Cleanup service for orphaned upload sessions."""
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
from database import Database
from logging_config import get_logger

logger = get_logger(__name__)


class CleanupService:
    """Service for cleaning up orphaned upload sessions."""
    
    def __init__(self, db: Database, interval_seconds: int = 600):
        """
        Initialize cleanup service.
        
        Args:
            db: Database instance
            interval_seconds: Cleanup interval in seconds (default: 600 = 10 minutes)
        """
        self.db = db
        self.interval_seconds = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
    
    def start(self) -> None:
        """Start the cleanup job in a background thread."""
        if self._running:
            logger.warning("Cleanup service is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_cleanup_loop, daemon=True)
        self._thread.start()
        logger.info(f"Cleanup service started (interval: {self.interval_seconds}s)")
    
    def stop(self) -> None:
        """Stop the cleanup job."""
        if not self._running:
            return
        
        logger.info("Stopping cleanup service...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        logger.info("Cleanup service stopped")
    
    def _run_cleanup_loop(self) -> None:
        """Main cleanup loop that runs in background thread."""
        while not self._stop_event.is_set():
            try:
                self.cleanup_orphaned_uploads()
            except Exception as e:
                logger.error(f"Error in cleanup job: {e}", exc_info=True)
            
            # Wait for next interval or stop event
            self._stop_event.wait(self.interval_seconds)
    
    def cleanup_orphaned_uploads(self) -> int:
        """
        Clean up orphaned upload sessions.
        
        Finds files with status='UPLOADING' that were created more than 1 hour ago
        and updates their status to 'DELETED'.
        
        Returns:
            Number of orphaned uploads cleaned
        """
        try:
            # Query for orphaned uploads (UPLOADING status, created > 1 hour ago)
            query = """
                UPDATE files
                SET status = 'DELETED'
                WHERE status = 'UPLOADING'
                  AND created_at < NOW() - INTERVAL '1 hour'
                RETURNING id
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(query)
                cleaned_records = cursor.fetchall()
                count = len(cleaned_records)
            
            if count > 0:
                logger.info(f"Cleaned up {count} orphaned upload(s)")
                # Log file IDs for debugging
                file_ids = [str(record['id']) for record in cleaned_records]
                logger.debug(f"Cleaned file IDs: {file_ids}")
            else:
                logger.debug("No orphaned uploads found")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned uploads: {e}", exc_info=True)
            raise
