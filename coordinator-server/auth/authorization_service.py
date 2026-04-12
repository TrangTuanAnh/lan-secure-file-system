"""Authorization service for permission checking based on room membership and roles."""
from typing import Optional
from database import Database
from logging_config import get_logger

logger = get_logger(__name__)


class AuthorizationService:
    """Handles permission checking for room-based actions."""
    
    # Permission matrix: role -> action -> allowed
    PERMISSION_MATRIX = {
        'ADMIN': {
            'CREATE_ROOM': True,
            'ADD_MEMBER': True,
            'REMOVE_MEMBER': True,
            'CHANGE_ROLE': True,
            'UPLOAD_FILE': True,
            'DOWNLOAD_FILE': True,
            'VIEW_FILES': True,
            'CREATE_SHARE_TOKEN': True,
            'DELETE_FILE': True,
        },
        'OWNER': {
            'CREATE_ROOM': False,
            'ADD_MEMBER': True,
            'REMOVE_MEMBER': True,
            'CHANGE_ROLE': True,
            'UPLOAD_FILE': True,
            'DOWNLOAD_FILE': True,
            'VIEW_FILES': True,
            'CREATE_SHARE_TOKEN': True,
            'DELETE_FILE': True,
        },
        'MEMBER': {
            'CREATE_ROOM': False,
            'ADD_MEMBER': False,
            'REMOVE_MEMBER': False,
            'CHANGE_ROLE': False,
            'UPLOAD_FILE': True,
            'DOWNLOAD_FILE': True,
            'VIEW_FILES': True,
            'CREATE_SHARE_TOKEN': True,
            'DELETE_FILE': False,
        },
        'VIEWER': {
            'CREATE_ROOM': False,
            'ADD_MEMBER': False,
            'REMOVE_MEMBER': False,
            'CHANGE_ROLE': False,
            'UPLOAD_FILE': False,
            'DOWNLOAD_FILE': True,
            'VIEW_FILES': True,
            'CREATE_SHARE_TOKEN': False,
            'DELETE_FILE': False,
        }
    }
    
    def __init__(self, database: Database):
        """
        Initialize authorization service.
        
        Args:
            database: Database instance
        """
        self.db = database
    
    def check_permission(self, user_id: str, global_role: str, room_id: Optional[str], action: str) -> bool:
        """
        Check if user has permission to perform action in room.
        
        Args:
            user_id: User identifier
            global_role: User's global role (USER or ADMIN)
            room_id: Room identifier (None for global actions like CREATE_ROOM)
            action: Action to check (e.g., 'UPLOAD_FILE', 'ADD_MEMBER')
        
        Returns:
            True if user has permission, False otherwise
        """
        # ADMIN has permission for all actions in all rooms
        if global_role == 'ADMIN':
            logger.debug(f"Permission granted: user {user_id} is ADMIN")
            return True
        
        # For CREATE_ROOM action, only ADMIN is allowed
        if action == 'CREATE_ROOM':
            logger.debug(f"Permission denied: user {user_id} is not ADMIN for CREATE_ROOM")
            return False
        
        # For room-specific actions, check room membership
        if room_id is None:
            logger.warning(f"Permission check failed: room_id is None for action {action}")
            return False
        
        # Query room_members table for user's role in room
        members = self.db.execute_query(
            "SELECT role FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, user_id)
        )
        
        # User is not a member of the room
        if not members:
            logger.debug(f"Permission denied: user {user_id} is not a member of room {room_id}")
            return False
        
        room_role = members[0]['role']
        
        # Check permission matrix for role and action combination
        has_permission = self._check_permission_matrix(room_role, action)
        
        if has_permission:
            logger.debug(f"Permission granted: user {user_id} has role {room_role} in room {room_id} for action {action}")
        else:
            logger.debug(f"Permission denied: user {user_id} with role {room_role} cannot perform {action}")
        
        return has_permission
    
    def _check_permission_matrix(self, role: str, action: str) -> bool:
        """
        Look up permission in the permission matrix.
        
        Args:
            role: User's role in the room (OWNER, MEMBER, VIEWER)
            action: Action to check
        
        Returns:
            True if role has permission for action, False otherwise
        """
        # Check if role exists in matrix
        if role not in self.PERMISSION_MATRIX:
            logger.warning(f"Unknown role: {role}")
            return False
        
        # Check if action exists for role
        role_permissions = self.PERMISSION_MATRIX[role]
        if action not in role_permissions:
            logger.warning(f"Unknown action: {action} for role {role}")
            return False
        
        return role_permissions[action]
    
    def get_user_role_in_room(self, user_id: str, room_id: str) -> Optional[str]:
        """
        Get user's role in a specific room.
        
        Args:
            user_id: User identifier
            room_id: Room identifier
        
        Returns:
            Role string (OWNER, MEMBER, VIEWER) or None if not a member
        """
        members = self.db.execute_query(
            "SELECT role FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, user_id)
        )
        
        if not members:
            return None
        
        return members[0]['role']
