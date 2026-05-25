"""Message handlers for upload control operations."""
from typing import Dict, Any
from protocol.message import Message
from protocol.message_types import MessageType
from upload.upload_service import UploadService
from logging_config import get_logger

logger = get_logger(__name__)


class UploadHandlers:
    """Handles upload control protocol messages."""
    
    def __init__(self, upload_service: UploadService):
        """
        Initialize upload handlers.
        
        Args:
            upload_service: UploadService instance
        """
        self.upload_service = upload_service
    
    def handle_init_upload(
        self,
        message: Message,
        user_id: str,
        global_role: str
    ) -> Message:
        """
        Handle INIT_UPLOAD request.
        
        Args:
            message: Incoming message
            user_id: Authenticated user ID
            global_role: User's global role
        
        Returns:
            Response message (UPLOAD_PLAN or ERROR)
        """
        payload = message.payload
        
        # Extract required fields
        room_id = payload.get('roomId')
        file_info = payload.get('fileInfo')
        storage_address = payload.get('storageAddress')
        
        # Validate required fields
        if not room_id or not file_info:
            return Message.create_error(
                "INVALID_INPUT",
                "roomId and fileInfo are required",
                request_id=message.request_id
            )
        
        # Call upload service
        success, upload_plan, error_code = self.upload_service.handle_init_upload(
            user_id=user_id,
            global_role=global_role,
            room_id=room_id,
            file_info=file_info,
            storage_address=storage_address
        )
        
        if not success:
            error_messages = {
                "PERMISSION_DENIED": "You do not have permission to upload files to this room",
                "INVALID_INPUT": "Invalid file information provided",
                "DUPLICATE_FILE_IN_ROOM": "A file with identical content already exists in this room",
                "STORAGE_NODE_UNAVAILABLE": "No healthy storage node is available",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to initialize upload"),
                request_id=message.request_id
            )
        
        # Return UPLOAD_PLAN
        return Message.create_response(
            MessageType.UPLOAD_PLAN,
            upload_plan,
            request_id=message.request_id
        )
    
    def handle_upload_complete(
        self,
        message: Message
    ) -> Message:
        """
        Handle UPLOAD_COMPLETE message from Storage Node.
        
        Args:
            message: Incoming message from Storage Node
        
        Returns:
            ACK message
        """
        payload = message.payload
        
        # Extract required fields
        file_id = payload.get('fileId')
        sha256_whole = payload.get('sha256Whole')
        stored_name = payload.get('storedName')
        final_size = payload.get('finalSize')
        storage_node_id = payload.get('storageNodeId')
        
        # Validate required fields
        if not all([file_id, sha256_whole, stored_name, final_size is not None]):
            return Message.create_error(
                "INVALID_INPUT",
                "fileId, sha256Whole, storedName, and finalSize are required",
                request_id=message.request_id
            )
        
        # Call upload service
        success, error_code = self.upload_service.handle_upload_complete(
            file_id=file_id,
            sha256_whole=sha256_whole,
            stored_name=stored_name,
            final_size=final_size,
            storage_node_id=storage_node_id
        )
        
        if not success:
            error_messages = {
                "FILE_NOT_FOUND": "File not found",
                "HASH_MISMATCH": "File hash does not match expected value",
                "STORAGE_NODE_MISMATCH": "Storage node does not match the file assignment",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to process upload completion"),
                request_id=message.request_id
            )
        
        # Return ACK
        return Message.create_response(
            MessageType.ACK,
            {"success": True, "fileId": file_id},
            request_id=message.request_id
        )
    
    def handle_upload_failed(
        self,
        message: Message
    ) -> Message:
        """
        Handle UPLOAD_FAILED message from Storage Node.
        
        Args:
            message: Incoming message from Storage Node
        
        Returns:
            ACK message
        """
        payload = message.payload
        
        # Extract required fields
        file_id = payload.get('fileId')
        reason = payload.get('reason', 'unknown')
        storage_node_id = payload.get('storageNodeId')
        
        # Validate required fields
        if not file_id:
            return Message.create_error(
                "INVALID_INPUT",
                "fileId is required",
                request_id=message.request_id
            )
        
        # Call upload service
        success, error_code = self.upload_service.handle_upload_failed(
            file_id=file_id,
            reason=reason,
            storage_node_id=storage_node_id
        )
        
        if not success:
            error_messages = {
                "FILE_NOT_FOUND": "File not found",
                "STORAGE_NODE_MISMATCH": "Storage node does not match the file assignment",
                "DATABASE_ERROR": "Database error occurred"
            }
            return Message.create_error(
                error_code,
                error_messages.get(error_code, "Failed to process upload failure"),
                request_id=message.request_id
            )
        
        # Return ACK
        return Message.create_response(
            MessageType.ACK,
            {"success": True, "fileId": file_id},
            request_id=message.request_id
        )
