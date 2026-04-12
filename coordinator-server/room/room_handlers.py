"""Message handlers for room management operations."""
from typing import Dict, Any, Optional
from protocol.message import Message
from protocol.message_types import MessageType
from room.room_service import RoomService
from logging_config import get_logger

logger = get_logger(__name__)


class RoomHandlers:
    """Handles room management protocol messages."""
    
    def __init__(self, room_service: RoomService):
        """
        Initialize room handlers.
        
        Args:
            room_service: RoomService instance
        """
        self.room_service = room_service
    
    def handle_create_room(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle CREATE_ROOM request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        name = payload.get('name')
        
        if not name:
            return Message.create_error(
                "INVALID_INPUT",
                "Room name is required",
                request_id=message.request_id
            )
        
        success, room_data, error_code = self.room_service.create_room(
            user_id, global_role, name
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "Only ADMIN users can create rooms",
                "INVALID_INPUT": "Invalid room name",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to create room"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.CREATE_ROOM_RESPONSE,
            room_data,
            request_id=message.request_id
        )
    
    def handle_add_member(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle ADD_MEMBER request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        room_id = payload.get('roomId')
        target_user_id = payload.get('userId')
        role = payload.get('role')
        
        if not room_id or not target_user_id or not role:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId, userId, and role are required",
                request_id=message.request_id
            )
        
        success, error_code = self.room_service.add_member(
            user_id, global_role, room_id, target_user_id, role
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have permission to add members to this room",
                "INVALID_ROLE": "Invalid role specified",
                "USER_NOT_FOUND": "Target user not found",
                "ALREADY_MEMBER": "User is already a member of this room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to add member"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.ADD_MEMBER_RESPONSE,
            {
                "success": True,
                "roomId": room_id,
                "userId": target_user_id,
                "role": role
            },
            request_id=message.request_id
        )
    
    def handle_remove_member(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle REMOVE_MEMBER request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        room_id = payload.get('roomId')
        target_user_id = payload.get('userId')
        
        if not room_id or not target_user_id:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId and userId are required",
                request_id=message.request_id
            )
        
        success, error_code = self.room_service.remove_member(
            user_id, global_role, room_id, target_user_id
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have permission to remove members from this room",
                "USER_NOT_MEMBER": "User is not a member of this room",
                "CANNOT_REMOVE_LAST_OWNER": "Cannot remove the last owner from the room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to remove member"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.REMOVE_MEMBER_RESPONSE,
            {
                "success": True,
                "roomId": room_id,
                "userId": target_user_id
            },
            request_id=message.request_id
        )
    
    def handle_set_role(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle SET_ROLE request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        room_id = payload.get('roomId')
        target_user_id = payload.get('userId')
        new_role = payload.get('role')
        
        if not room_id or not target_user_id or not new_role:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId, userId, and role are required",
                request_id=message.request_id
            )
        
        success, error_code = self.room_service.set_role(
            user_id, global_role, room_id, target_user_id, new_role
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have permission to change roles in this room",
                "CANNOT_CHANGE_OWN_ROLE": "You cannot change your own role",
                "INVALID_ROLE": "Invalid role specified",
                "USER_NOT_MEMBER": "User is not a member of this room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to change role"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.SET_ROLE_RESPONSE,
            {
                "success": True,
                "roomId": room_id,
                "userId": target_user_id,
                "role": new_role
            },
            request_id=message.request_id
        )
    
    def handle_list_rooms(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle LIST_ROOMS request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        success, rooms_list, error_code = self.room_service.list_rooms(
            user_id, global_role
        )
        
        if not success:
            return Message.create_error(
                error_code,
                "Failed to list rooms",
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.LIST_ROOMS_RESPONSE,
            {"rooms": rooms_list},
            request_id=message.request_id
        )
    
    def handle_list_members(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle LIST_MEMBERS request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        room_id = payload.get('roomId')
        
        if not room_id:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId is required",
                request_id=message.request_id
            )
        
        success, members_list, error_code = self.room_service.list_members(
            user_id, global_role, room_id
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have access to this room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to list members"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.LIST_MEMBERS_RESPONSE,
            {
                "roomId": room_id,
                "members": members_list
            },
            request_id=message.request_id
        )
