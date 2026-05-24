"""File metadata service for managing file records."""
from typing import Optional, Dict, Any, List, Tuple
from database import Database
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from logging_config import get_logger

logger = get_logger(__name__)


class FileService:
    """Handles file metadata operations."""
    
    def __init__(
        self,
        database: Database,
        audit_service: Optional[AuditService] = None,
        notification_service: Optional[NotificationService] = None
    ):
        """
        Initialize file service.
        
        Args:
            database: Database instance
            audit_service: Optional audit service for logging
            notification_service: Optional notification service for broadcasting
        """
        self.db = database
        self.audit = audit_service
        self.notification = notification_service
    
    def list_files(
        self,
        user_id: str,
        global_role: str,
        room_id: str
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        List all files in a room with status READY.
        
        Args:
            user_id: User requesting the list
            global_role: User's global role
            room_id: Room identifier
        
        Returns:
            Tuple of (success, files_list, error_code)
        """
        # Verify user is member of room or ADMIN
        if not self._has_room_access(user_id, global_role, room_id):
            logger.info(f"LIST_FILES denied: user {user_id} does not have access to room {room_id}")
            return False, None, "PERMISSION_DENIED"
        
        try:
            # Query files table WHERE room_id matches and status = 'READY'
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                       f.uploader_id, f.size_bytes, f.mime_type, f.sha256_whole,
                       f.total_chunks, f.chunk_size, f.status, f.created_at,
                       u.username as uploader_username
                FROM files f
                JOIN users u ON f.uploader_id = u.id
                WHERE f.room_id = %s AND f.status = %s
                ORDER BY f.created_at DESC
                """,
                (room_id, 'READY')
            )
            
            # Format results
            files_list = []
            for file in files:
                file_data = {
                    "fileId": file['id'],
                    "roomId": file['room_id'],
                    "originalName": file['original_name'],
                    "storedName": file['stored_name'],
                    "version": file['version'],
                    "uploaderId": file['uploader_id'],
                    "uploaderUsername": file['uploader_username'],
                    "sizeBytes": file['size_bytes'],
                    "mimeType": file['mime_type'],
                    "sha256Whole": file['sha256_whole'],
                    "totalChunks": file['total_chunks'],
                    "chunkSize": file['chunk_size'],
                    "status": file['status'],
                    "createdAt": file['created_at'].isoformat() if hasattr(file['created_at'], 'isoformat') else str(file['created_at'])
                }
                files_list.append(file_data)
            
            logger.debug(f"LIST_FILES: returned {len(files_list)} files for room {room_id}")
            return True, files_list, None
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return False, None, "DATABASE_ERROR"
    
    def get_file_detail(
        self,
        user_id: str,
        global_role: str,
        file_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get details of a single file.
        
        Args:
            user_id: User requesting the details
            global_role: User's global role
            file_id: File identifier
        
        Returns:
            Tuple of (success, file_data, error_code)
        """
        try:
            # Query single file record by ID
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                       f.uploader_id, f.size_bytes, f.mime_type, f.sha256_whole,
                       f.total_chunks, f.chunk_size, f.status, f.created_at,
                       u.username as uploader_username
                FROM files f
                JOIN users u ON f.uploader_id = u.id
                WHERE f.id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.info(f"FILE_DETAIL failed: file {file_id} not found")
                return False, None, "FILE_NOT_FOUND"
            
            file = files[0]
            room_id = file['room_id']
            
            # Verify user has access to file's room
            if not self._has_room_access(user_id, global_role, room_id):
                logger.info(f"FILE_DETAIL denied: user {user_id} does not have access to room {room_id}")
                return False, None, "PERMISSION_DENIED"
            
            # Format result
            file_data = {
                "fileId": file['id'],
                "roomId": file['room_id'],
                "originalName": file['original_name'],
                "storedName": file['stored_name'],
                "version": file['version'],
                "uploaderId": file['uploader_id'],
                "uploaderUsername": file['uploader_username'],
                "sizeBytes": file['size_bytes'],
                "mimeType": file['mime_type'],
                "sha256Whole": file['sha256_whole'],
                "totalChunks": file['total_chunks'],
                "chunkSize": file['chunk_size'],
                "status": file['status'],
                "createdAt": file['created_at'].isoformat() if hasattr(file['created_at'], 'isoformat') else str(file['created_at'])
            }
            
            logger.debug(f"FILE_DETAIL: returned details for file {file_id}")
            return True, file_data, None
            
        except Exception as e:
            logger.error(f"Failed to get file detail: {e}")
            return False, None, "DATABASE_ERROR"
    
    def get_file_versions(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        original_name: str
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get all versions of a file with the same name in a room.
        
        Args:
            user_id: User requesting the versions
            global_role: User's global role
            room_id: Room identifier
            original_name: Original filename
        
        Returns:
            Tuple of (success, versions_list, error_code)
        """
        # Verify user has access to room
        if not self._has_room_access(user_id, global_role, room_id):
            logger.info(f"FILE_VERSIONS denied: user {user_id} does not have access to room {room_id}")
            return False, None, "PERMISSION_DENIED"
        
        try:
            # Query files WHERE room_id and original_name match, ordered by version descending
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                       f.uploader_id, f.size_bytes, f.mime_type, f.sha256_whole,
                       f.total_chunks, f.chunk_size, f.status, f.created_at,
                       u.username as uploader_username
                FROM files f
                JOIN users u ON f.uploader_id = u.id
                WHERE f.room_id = %s AND f.original_name = %s
                ORDER BY f.version DESC
                """,
                (room_id, original_name)
            )
            
            # Format results
            versions_list = []
            for file in files:
                file_data = {
                    "fileId": file['id'],
                    "roomId": file['room_id'],
                    "originalName": file['original_name'],
                    "storedName": file['stored_name'],
                    "version": file['version'],
                    "uploaderId": file['uploader_id'],
                    "uploaderUsername": file['uploader_username'],
                    "sizeBytes": file['size_bytes'],
                    "mimeType": file['mime_type'],
                    "sha256Whole": file['sha256_whole'],
                    "totalChunks": file['total_chunks'],
                    "chunkSize": file['chunk_size'],
                    "status": file['status'],
                    "createdAt": file['created_at'].isoformat() if hasattr(file['created_at'], 'isoformat') else str(file['created_at'])
                }
                versions_list.append(file_data)
            
            logger.debug(f"FILE_VERSIONS: returned {len(versions_list)} versions for {original_name} in room {room_id}")
            return True, versions_list, None
            
        except Exception as e:
            logger.error(f"Failed to get file versions: {e}")
            return False, None, "DATABASE_ERROR"
    
    def delete_file(
        self,
        user_id: str,
        global_role: str,
        file_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a file (soft delete by updating status to DELETED).
        
        Args:
            user_id: User performing the deletion
            global_role: User's global role
            file_id: File identifier
        
        Returns:
            Tuple of (success, error_code)
        """
        try:
            # Get file details to check room ownership
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name, f.uploader_id
                FROM files f
                WHERE f.id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.info(f"DELETE_FILE failed: file {file_id} not found")
                return False, "FILE_NOT_FOUND"
            
            file = files[0]
            room_id = file['room_id']
            original_name = file['original_name']
            uploader_id = file['uploader_id']
            
            # Verify user is ADMIN, OWNER of file's room, or uploader of the file
            if not self._can_delete_file(user_id, global_role, room_id, uploader_id):
                logger.info(
                    "DELETE_FILE denied: user %s is not ADMIN, OWNER, or uploader for room %s file %s",
                    user_id,
                    room_id,
                    file_id,
                )
                return False, "PERMISSION_DENIED"
            
            # Update file status to 'DELETED'
            self.db.execute_update(
                "UPDATE files SET status = %s WHERE id = %s",
                ('DELETED', file_id)
            )
            
            logger.info(f"File deleted: {file_id} (name={original_name}, room={room_id})")
            
            # Broadcast FILE_DELETED notification
            if self.notification:
                self.notification.broadcast_file_deleted(room_id, file_id, original_name, user_id)
            
            # Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='DELETE_FILE',
                    target_type='file',
                    target_id=file_id,
                    room_id=room_id,
                    detail={'original_name': original_name},
                    status='SUCCESS'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False, "DATABASE_ERROR"
    
    def calculate_next_version(
        self,
        room_id: str,
        original_name: str
    ) -> int:
        """
        Calculate the next version number for a file.
        
        Args:
            room_id: Room identifier
            original_name: Original filename
        
        Returns:
            Next version number (MAX + 1, or 1 if no previous version)
        """
        try:
            # Query MAX(version) FROM files WHERE room_id and original_name match
            result = self.db.execute_query(
                """
                SELECT MAX(version) as max_version
                FROM files
                WHERE room_id = %s AND original_name = %s
                """,
                (room_id, original_name)
            )
            
            if result and result[0]['max_version'] is not None:
                next_version = result[0]['max_version'] + 1
                logger.debug(f"Next version for {original_name} in room {room_id}: {next_version}")
                return next_version
            else:
                logger.debug(f"First version for {original_name} in room {room_id}: 1")
                return 1
                
        except Exception as e:
            logger.error(f"Failed to calculate next version: {e}")
            # Default to version 1 on error
            return 1
    
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
    
    def _can_delete_file(self, user_id: str, global_role: str, room_id: str, uploader_id: str) -> bool:
        """
        Check if user can delete files (ADMIN, OWNER, or original uploader).
        
        Args:
            user_id: User identifier
            global_role: User's global role
            room_id: Room identifier
        
        Returns:
            True if user can delete files
        """
        # ADMIN can delete all files
        if global_role == 'ADMIN':
            return True
        
        # Original uploader can delete their own file.
        if uploader_id and str(uploader_id) == str(user_id):
            return True

        # Check if user is OWNER of the room
        members = self.db.execute_query(
            "SELECT role FROM room_members WHERE room_id = %s AND user_id = %s",
            (room_id, user_id)
        )
        
        return members and members[0]['role'] == 'OWNER'
