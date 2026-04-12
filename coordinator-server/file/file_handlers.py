"""Message handlers for file metadata operations."""
from typing import Dict, Any, Optional
from protocol.message import Message
from protocol.message_types import MessageType
from file.file_service import FileService
from logging_config import get_logger

logger = get_logger(__name__)


class FileHandlers:
    """Handles file metadata protocol messages."""
    
    def __init__(self, file_service: FileService):
        """
        Initialize file handlers.
        
        Args:
            file_service: FileService instance
        """
        self.file_service = file_service
    
    def handle_list_files(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle LIST_FILES request.
        
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
        
        success, files_list, error_code = self.file_service.list_files(
            user_id, global_role, room_id
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have access to this room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to list files"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.LIST_FILES_RESPONSE,
            {
                "roomId": room_id,
                "files": files_list
            },
            request_id=message.request_id
        )
    
    def handle_file_detail(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle FILE_DETAIL request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        file_id = payload.get('fileId')
        
        if not file_id:
            return Message.create_error(
                "INVALID_INPUT",
                "fileId is required",
                request_id=message.request_id
            )
        
        success, file_data, error_code = self.file_service.get_file_detail(
            user_id, global_role, file_id
        )
        
        if not success:
            error_messages = {
                "FILE_NOT_FOUND": "File not found",
                "PERMISSION_DENIED": "You do not have access to this file",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to get file details"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.FILE_DETAIL_RESPONSE,
            file_data,
            request_id=message.request_id
        )
    
    def handle_file_versions(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle FILE_VERSIONS request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        room_id = payload.get('roomId')
        original_name = payload.get('originalName')
        
        if not room_id or not original_name:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId and originalName are required",
                request_id=message.request_id
            )
        
        success, versions_list, error_code = self.file_service.get_file_versions(
            user_id, global_role, room_id, original_name
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have access to this room",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to get file versions"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.FILE_VERSIONS_RESPONSE,
            {
                "roomId": room_id,
                "originalName": original_name,
                "versions": versions_list
            },
            request_id=message.request_id
        )
    
    def handle_delete_file(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle DELETE_FILE request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message
        """
        payload = message.payload
        file_id = payload.get('fileId')
        
        if not file_id:
            return Message.create_error(
                "INVALID_INPUT",
                "fileId is required",
                request_id=message.request_id
            )
        
        success, error_code = self.file_service.delete_file(
            user_id, global_role, file_id
        )
        
        if not success:
            error_messages = {
                "FILE_NOT_FOUND": "File not found",
                "PERMISSION_DENIED": "You do not have permission to delete this file",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to delete file"),
                request_id=message.request_id
            )
        
        return Message.create_response(
            MessageType.DELETE_FILE_RESPONSE,
            {
                "success": True,
                "fileId": file_id
            },
            request_id=message.request_id
        )
