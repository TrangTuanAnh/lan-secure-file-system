"""Room management service for creating rooms and managing members."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from database import Database
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from logging_config import get_logger

logger = get_logger(__name__)


class RoomService:
    """Handles room management operations."""
    
    def __init__(
        self,
        database: Database,
        audit_service: Optional[AuditService] = None,
        notification_service: Optional[NotificationService] = None
    ):
        """
        Initialize room service.
        
        Args:
            database: Database instance
            audit_service: Optional audit service for logging
            notification_service: Optional notification service for broadcasting
        """
        self.db = database
        self.audit = audit_service
        self.notification = notification_service
    
    def create_room(self, user_id: str, global_role: str, name: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Create a new room.
        
        Args:
            user_id: User creating the room
            global_role: User's global role
            name: Room name
        
        Returns:
            Tuple of (success, room_data, error_code)
            - success: True if room created
            - room_data: Dict with room details if successful
            - error_code: Error code if failed (PERMISSION_DENIED)
        """
        # Verify user has globalRole ADMIN
        if global_role != 'ADMIN':
            logger.info(f"CREATE_ROOM denied: user {user_id} is not ADMIN")
            return False, None, "PERMISSION_DENIED"
        
        # Validate input
        if not name or not name.strip():
            return False, None, "INVALID_INPUT"
        
        room_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        try:
            # Insert room record
            self.db.execute_update(
                """
                INSERT INTO rooms (id, name, created_by, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (room_id, name.strip(), user_id, now)
            )
            
            # Add creator as OWNER in room_members
            self.db.execute_update(
                """
                INSERT INTO room_members (room_id, user_id, role, added_at)
                VALUES (%s, %s, %s, %s)
                """,
                (room_id, user_id, 'OWNER', now)
            )
            
            logger.info(f"Room created: {room_id} (name={name}, creator={user_id})")
            
            # Write audit log
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='CREATE_ROOM',
                    target_type='room',
                    target_id=room_id,
                    room_id=room_id,
                    detail={'name': name},
                    status='SUCCESS'
                )
            
            room_data = {
                "roomId": room_id,
                "name": name,
                "createdBy": user_id,
                "createdAt": now.isoformat()
            }
            
            return True, room_data, None
            
        except Exception as e:
            logger.error(f"Failed to create room: {e}")
            return False, None, "DATABASE_ERROR"
    
    def add_member(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        target_user_id: str,
        role: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Add a member to a room.
        
        Args:
            user_id: User performing the action
            global_role: User's global role
            room_id: Room identifier
            target_user_id: User to add
            role: Role to assign (OWNER, MEMBER, VIEWER)
        
        Returns:
            Tuple of (success, error_code)
        """
        # Verify requesting user is ADMIN or OWNER
        if not self._can_manage_members(user_id, global_role, room_id):
            logger.info(f"ADD_MEMBER denied: user {user_id} is not ADMIN or OWNER of room {room_id}")
            return False, "PERMISSION_DENIED"
        
        # Validate role
        if role not in ['OWNER', 'MEMBER', 'VIEWER']:
            return False, "INVALID_ROLE"
        
        # Verify target user exists
        target_users = self.db.execute_query(
            "SELECT id, username FROM users WHERE id = %s",
            (target_user_id,)
        )
        
        if not target_users:
            logger.info(f"ADD_MEMBER failed: target user {target_user_id} not found")
            return False, "USER_NOT_FOUND"
        
        target_username = target_users[0]['username']
        
        # Verify target user is not already a member
        existing_members = self.db.execute_query(
            "SELECT user_id FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, target_user_id)
        )
        
        if existing_members:
            logger.info(f"ADD_MEMBER failed: user {target_user_id} is already a member of room {room_id}")
            return False, "ALREADY_MEMBER"
        
        # Insert record into room_members
        now = datetime.now(timezone.utc)
        
        try:
            self.db.execute_update(
                """
                INSERT INTO room_members (room_id, user_id, role, added_at)
                VALUES (%s, %s, %s, %s)
                """,
                (room_id, target_user_id, role, now)
            )
            
            logger.info(f"Member added: user {target_user_id} added to room {room_id} with role {role}")
            
            # Broadcast notification
            if self.notification:
                self.notification.broadcast_member_added(room_id, target_user_id, target_username, role)
            
            # Write audit log
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='ADD_MEMBER',
                    target_type='room_member',
                    target_id=target_user_id,
                    room_id=room_id,
                    detail={'role': role},
                    status='SUCCESS'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to add member: {e}")
            return False, "DATABASE_ERROR"
    
    def remove_member(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        target_user_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Remove a member from a room.
        
        Args:
            user_id: User performing the action
            global_role: User's global role
            room_id: Room identifier
            target_user_id: User to remove
        
        Returns:
            Tuple of (success, error_code)
        """
        # Verify requesting user is ADMIN or OWNER
        if not self._can_manage_members(user_id, global_role, room_id):
            logger.info(f"REMOVE_MEMBER denied: user {user_id} is not ADMIN or OWNER of room {room_id}")
            return False, "PERMISSION_DENIED"
        
        # Check if target user is a member
        target_members = self.db.execute_query(
            "SELECT rm.role, u.username FROM room_members rm JOIN users u ON rm.user_id = u.id WHERE rm.room_id = %s AND rm.user_id = %s",
            (room_id, target_user_id)
        )
        
        if not target_members:
            logger.info(f"REMOVE_MEMBER failed: user {target_user_id} is not a member of room {room_id}")
            return False, "USER_NOT_MEMBER"
        
        target_role = target_members[0]['role']
        target_username = target_members[0]['username']
        
        # Check if removing member would leave no OWNER
        if target_role == 'OWNER':
            owner_count = self.db.execute_query(
                "SELECT COUNT(*) as count FROM room_members WHERE room_id = %s AND role = %s",
                (room_id, 'OWNER')
            )
            
            if owner_count and owner_count[0]['count'] <= 1:
                logger.info(f"REMOVE_MEMBER denied: cannot remove last OWNER from room {room_id}")
                return False, "CANNOT_REMOVE_LAST_OWNER"
        
        # Delete record from room_members
        try:
            self.db.execute_update(
                "DELETE FROM room_members WHERE room_id = %s AND user_id = %s",
                (room_id, target_user_id)
            )
            
            logger.info(f"Member removed: user {target_user_id} removed from room {room_id}")
            
            # Broadcast notification
            if self.notification:
                self.notification.broadcast_member_removed(room_id, target_user_id, target_username)
            
            # Write audit log
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='REMOVE_MEMBER',
                    target_type='room_member',
                    target_id=target_user_id,
                    room_id=room_id,
                    detail={'removed_role': target_role},
                    status='SUCCESS'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to remove member: {e}")
            return False, "DATABASE_ERROR"
    
    def set_role(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        target_user_id: str,
        new_role: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Change a member's role in a room.
        
        Args:
            user_id: User performing the action
            global_role: User's global role
            room_id: Room identifier
            target_user_id: User whose role to change
            new_role: New role to assign
        
        Returns:
            Tuple of (success, error_code)
        """
        # Verify requesting user is ADMIN or OWNER
        if not self._can_manage_members(user_id, global_role, room_id):
            logger.info(f"SET_ROLE denied: user {user_id} is not ADMIN or OWNER of room {room_id}")
            return False, "PERMISSION_DENIED"
        
        # Verify user is not changing their own role
        if user_id == target_user_id:
            logger.info(f"SET_ROLE denied: user {user_id} cannot change their own role")
            return False, "CANNOT_CHANGE_OWN_ROLE"
        
        # Validate role
        if new_role not in ['OWNER', 'MEMBER', 'VIEWER']:
            return False, "INVALID_ROLE"
        
        # Check if target user is a member
        target_members = self.db.execute_query(
            "SELECT rm.role, u.username FROM room_members rm JOIN users u ON rm.user_id = u.id WHERE rm.room_id = %s AND rm.user_id = %s",
            (room_id, target_user_id)
        )
        
        if not target_members:
            logger.info(f"SET_ROLE failed: user {target_user_id} is not a member of room {room_id}")
            return False, "USER_NOT_MEMBER"
        
        old_role = target_members[0]['role']
        target_username = target_members[0]['username']
        
        # Update role in room_members
        try:
            self.db.execute_update(
                "UPDATE room_members SET role = %s WHERE room_id = %s AND user_id = %s",
                (new_role, room_id, target_user_id)
            )
            
            logger.info(f"Role updated: user {target_user_id} in room {room_id} now has role {new_role}")
            
            # Broadcast notification
            if self.notification:
                self.notification.broadcast_role_updated(room_id, target_user_id, target_username, new_role)
            
            # Write audit log
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='SET_ROLE',
                    target_type='room_member',
                    target_id=target_user_id,
                    room_id=room_id,
                    detail={'old_role': old_role, 'new_role': new_role},
                    status='SUCCESS'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to update role: {e}")
            return False, "DATABASE_ERROR"
    
    def list_rooms(self, user_id: str, global_role: str) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        List all rooms where user is a member (or all rooms if ADMIN).
        
        Args:
            user_id: User identifier
            global_role: User's global role
        
        Returns:
            Tuple of (success, rooms_list, error_code)
        """
        try:
            if global_role == 'ADMIN':
                # Return all rooms
                rooms = self.db.execute_query(
                    """
                    SELECT r.id, r.name, r.created_by, r.created_at,
                           u.username as creator_username
                    FROM rooms r
                    JOIN users u ON r.created_by = u.id
                    ORDER BY r.created_at DESC
                    """
                )
            else:
                # Return only rooms where user is a member
                rooms = self.db.execute_query(
                    """
                    SELECT r.id, r.name, r.created_by, r.created_at,
                           u.username as creator_username,
                           rm.role as user_role
                    FROM rooms r
                    JOIN users u ON r.created_by = u.id
                    JOIN room_members rm ON r.id = rm.room_id
                    WHERE rm.user_id = %s
                    ORDER BY r.created_at DESC
                    """,
                    (user_id,)
                )
            
            # Format results
            rooms_list = []
            for room in rooms:
                room_data = {
                    "roomId": room['id'],
                    "name": room['name'],
                    "createdBy": room['created_by'],
                    "creatorUsername": room['creator_username'],
                    "createdAt": room['created_at'].isoformat() if hasattr(room['created_at'], 'isoformat') else str(room['created_at'])
                }
                
                # Add user role if not ADMIN
                if global_role != 'ADMIN' and 'user_role' in room:
                    room_data["userRole"] = room['user_role']
                
                rooms_list.append(room_data)
            
            logger.debug(f"LIST_ROOMS: returned {len(rooms_list)} rooms for user {user_id}")
            return True, rooms_list, None
            
        except Exception as e:
            logger.error(f"Failed to list rooms: {e}")
            return False, None, "DATABASE_ERROR"
    
    def list_members(
        self,
        user_id: str,
        global_role: str,
        room_id: str
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        List all members of a room.
        
        Args:
            user_id: User requesting the list
            global_role: User's global role
            room_id: Room identifier
        
        Returns:
            Tuple of (success, members_list, error_code)
        """
        # Verify user has access to room
        if not self._has_room_access(user_id, global_role, room_id):
            logger.info(f"LIST_MEMBERS denied: user {user_id} does not have access to room {room_id}")
            return False, None, "PERMISSION_DENIED"
        
        try:
            # Query room_members with user details
            members = self.db.execute_query(
                """
                SELECT rm.user_id, rm.role, rm.added_at,
                       u.username, u.email
                FROM room_members rm
                JOIN users u ON rm.user_id = u.id
                WHERE rm.room_id = %s
                ORDER BY rm.added_at ASC
                """,
                (room_id,)
            )
            
            # Format results
            members_list = []
            for member in members:
                member_data = {
                    "userId": member['user_id'],
                    "username": member['username'],
                    "email": member['email'],
                    "role": member['role'],
                    "addedAt": member['added_at'].isoformat() if hasattr(member['added_at'], 'isoformat') else str(member['added_at'])
                }
                members_list.append(member_data)
            
            logger.debug(f"LIST_MEMBERS: returned {len(members_list)} members for room {room_id}")
            return True, members_list, None
            
        except Exception as e:
            logger.error(f"Failed to list members: {e}")
            return False, None, "DATABASE_ERROR"
    
    def _can_manage_members(self, user_id: str, global_role: str, room_id: str) -> bool:
        """
        Check if user can manage members (ADMIN or OWNER).
        
        Args:
            user_id: User identifier
            global_role: User's global role
            room_id: Room identifier
        
        Returns:
            True if user can manage members
        """
        # ADMIN can manage all rooms
        if global_role == 'ADMIN':
            return True
        
        # Check if user is OWNER of the room
        members = self.db.execute_query(
            "SELECT role FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, user_id)
        )
        
        return members and members[0]['role'] == 'OWNER'
    
    def _has_room_access(self, user_id: str, global_role: str, room_id: str) -> bool:
        """
        Check if user has access to room (is member or ADMIN).
        
        Args:
            user_id: User identifier
            global_role: User's global role
            room_id: Room identifier
        
        Returns:
            True if user has access
        """
        # ADMIN has access to all rooms
        if global_role == 'ADMIN':
            return True
        
        # Check if user is a member
        members = self.db.execute_query(
            "SELECT user_id FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, user_id)
        )
        
        return len(members) > 0
