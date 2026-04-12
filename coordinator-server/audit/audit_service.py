"""Audit logging service for recording significant actions."""
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from database import Database
from logging_config import get_logger

logger = get_logger(__name__)


class AuditService:
    """Handles audit log writing for compliance and debugging."""
    
    def __init__(self, database: Database):
        """
        Initialize audit service.
        
        Args:
            database: Database instance
        """
        self.db = database
    
    def write_audit_log(
        self,
        actor_id: Optional[str],
        action: str,
        target_type: str,
        target_id: str,
        room_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        status: str = 'SUCCESS'
    ) -> bool:
        """
        Write an audit log entry synchronously.
        
        Args:
            actor_id: User who performed the action (None for anonymous)
            action: Action type (e.g., 'CREATE_ROOM', 'ADD_MEMBER')
            target_type: Type of target (e.g., 'room', 'room_member')
            target_id: Target identifier
            room_id: Related room (if applicable)
            detail: Additional structured data (stored as JSONB)
            status: 'SUCCESS' or 'FAILED'
        
        Returns:
            True if log entry was written successfully
        """
        now = datetime.now(timezone.utc)
        
        try:
            # Convert detail to JSON string if provided
            detail_json = json.dumps(detail) if detail else None
            
            self.db.execute_update(
                """
                INSERT INTO audit_logs (actor_id, action, target_type, target_id, room_id, detail, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (actor_id, action, target_type, target_id, room_id, detail_json, status, now)
            )
            
            logger.debug(f"Audit log written: action={action}, target={target_type}:{target_id}, status={status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            return False
