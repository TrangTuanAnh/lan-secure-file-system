"""Upload control service for file upload management."""
import uuid
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from database import Database
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from redis_client import RedisClient
from upload.scan_validator import ScanValidator
from upload.dedup_checker import DeduplicationChecker
from logging_config import get_logger

logger = get_logger(__name__)


class UploadService:
    """Handles file upload control plane operations."""
    
    def __init__(
        self,
        database: Database,
        redis_client: RedisClient,
        authorization_service: AuthorizationService,
        audit_service: Optional[AuditService] = None,
        notification_service: Optional[Any] = None,
        chunk_size: int = 524288,  # 512KB default
        ticket_ttl_seconds: int = 1800  # 30 minutes default
    ):
        """
        Initialize upload service.
        
        Args:
            database: Database instance
            redis_client: Redis client for ticket storage
            authorization_service: Authorization service for permission checks
            audit_service: Optional audit service for logging
            notification_service: Optional notification service for broadcasting events
            chunk_size: Default chunk size in bytes
            ticket_ttl_seconds: Ticket expiration time in seconds
        """
        self.db = database
        self.redis = redis_client
        self.authz = authorization_service
        self.audit = audit_service
        self.notification = notification_service
        self.chunk_size = chunk_size
        self.ticket_ttl_seconds = ticket_ttl_seconds
        
        # Initialize validators and checkers
        self.scan_validator = ScanValidator()
        self.dedup_checker = DeduplicationChecker(database)
    
    def handle_init_upload(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        file_info: Dict[str, Any],
        scan_report: Dict[str, Any],
        storage_address: str = "localhost:9000"  # Default storage node address
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Handle INIT_UPLOAD request.
        
        Process:
        1. Verify user has ADMIN, OWNER, or MEMBER role in room
        2. Validate scan report
        3. Check for deduplication
        4. If deduplicated: create file record with status READY, return deduplicated=true
        5. If not deduplicated: create file record with status UPLOADING, generate ticket
        
        Args:
            user_id: User initiating upload
            global_role: User's global role
            room_id: Target room ID
            file_info: File information dictionary with:
                - originalName: Original filename
                - sizeBytes: File size in bytes
                - mimeType: MIME type
                - sha256Whole: SHA256 hash of entire file
            scan_report: Scan report dictionary
            storage_address: Storage node address (host:port)
        
        Returns:
            Tuple of (success, upload_plan, error_code)
            upload_plan contains:
                - fileId: Created file ID
                - ticket: Upload ticket (if not deduplicated)
                - storageAddress: Storage node address
                - chunkSize: Chunk size in bytes
                - totalChunks: Number of chunks
                - deduplicated: Boolean flag
        """
        # Step 1: Verify user has ADMIN, OWNER, or MEMBER role in room
        if not self.authz.check_permission(user_id, global_role, room_id, 'UPLOAD_FILE'):
            logger.info(f"INIT_UPLOAD denied: user {user_id} lacks permission in room {room_id}")
            return False, None, "PERMISSION_DENIED"
        
        # Extract file info
        original_name = file_info.get('originalName')
        size_bytes = file_info.get('sizeBytes')
        mime_type = file_info.get('mimeType')
        sha256_whole = file_info.get('sha256Whole')
        
        # Validate required fields
        if not all([original_name, size_bytes is not None, mime_type, sha256_whole]):
            logger.warning("INIT_UPLOAD failed: missing required file info fields")
            return False, None, "INVALID_INPUT"
        
        # Step 2: Validate scan report
        is_valid, error_code = self.scan_validator.validate_scan_report(scan_report, sha256_whole)
        if not is_valid:
            logger.info(f"INIT_UPLOAD failed: scan validation error {error_code}")
            return False, None, error_code
        
        # Step 3: Check for deduplication
        existing_file = self.dedup_checker.check_deduplication(sha256_whole)
        
        # Calculate version number
        version = self._calculate_next_version(room_id, original_name)
        
        # Calculate total chunks
        total_chunks = math.ceil(size_bytes / self.chunk_size) if size_bytes > 0 else 1
        
        try:
            if existing_file:
                # Step 4: Deduplicated upload - create file record with status READY
                file_id = str(uuid.uuid4())
                stored_name = existing_file['stored_name']
                
                # Insert file record
                self.db.execute_update(
                    """
                    INSERT INTO files (
                        id, room_id, original_name, stored_name, version,
                        uploader_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, chunk_size, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id, room_id, original_name, stored_name, version,
                        user_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, self.chunk_size, 'READY', datetime.now(timezone.utc)
                    )
                )
                
                # Insert scan report
                self._insert_scan_report(file_id, scan_report, sha256_whole)
                
                logger.info(
                    f"Deduplicated upload: file_id={file_id}, "
                    f"stored_name={stored_name}, room={room_id}"
                )
                
                # Write audit log
                if self.audit:
                    self.audit.write_audit_log(
                        actor_id=user_id,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=room_id,
                        detail={
                            'original_name': original_name,
                            'size_bytes': size_bytes,
                            'deduplicated': True
                        },
                        status='SUCCESS'
                    )
                
                # Return upload plan with deduplicated flag
                return True, {
                    'fileId': file_id,
                    'storageAddress': storage_address,
                    'chunkSize': self.chunk_size,
                    'totalChunks': total_chunks,
                    'deduplicated': True
                }, None
            
            else:
                # Step 5: New upload - create file record with status UPLOADING
                file_id = str(uuid.uuid4())
                stored_name = f"{room_id}/{file_id}"
                
                # Insert file record with UPLOADING status
                self.db.execute_update(
                    """
                    INSERT INTO files (
                        id, room_id, original_name, stored_name, version,
                        uploader_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, chunk_size, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id, room_id, original_name, stored_name, version,
                        user_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, self.chunk_size, 'UPLOADING', datetime.now(timezone.utc)
                    )
                )
                
                # Insert scan report
                self._insert_scan_report(file_id, scan_report, sha256_whole)
                
                # Generate upload ticket
                ticket = str(uuid.uuid4())
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ticket_ttl_seconds)
                
                # Store ticket metadata in Redis
                ticket_data = {
                    'type': 'upload',
                    'fileId': file_id,
                    'userId': user_id,
                    'roomId': room_id,
                    'totalChunks': total_chunks,
                    'chunkSize': self.chunk_size,
                    'sha256Whole': sha256_whole,
                    'storedName': stored_name,
                    'expiresAt': expires_at.isoformat()
                }
                
                self.redis.set_ticket(ticket, ticket_data, self.ticket_ttl_seconds)
                
                logger.info(
                    f"New upload initialized: file_id={file_id}, "
                    f"ticket={ticket}, room={room_id}, chunks={total_chunks}"
                )
                
                # Return upload plan with ticket
                return True, {
                    'fileId': file_id,
                    'ticket': ticket,
                    'storageAddress': storage_address,
                    'chunkSize': self.chunk_size,
                    'totalChunks': total_chunks,
                    'deduplicated': False
                }, None
        
        except Exception as e:
            logger.error(f"Failed to initialize upload: {e}")
            return False, None, "DATABASE_ERROR"
    
    def _calculate_next_version(self, room_id: str, original_name: str) -> int:
        """
        Calculate next version number for a file.
        
        Args:
            room_id: Room identifier
            original_name: Original filename
        
        Returns:
            Next version number (MAX + 1, or 1 if no previous version)
        """
        try:
            result = self.db.execute_query(
                """
                SELECT MAX(version) as max_version
                FROM files
                WHERE room_id = %s AND original_name = %s
                """,
                (room_id, original_name)
            )
            
            if result and result[0]['max_version'] is not None:
                return result[0]['max_version'] + 1
            return 1
            
        except Exception as e:
            logger.error(f"Failed to calculate next version: {e}")
            return 1
    
    def _insert_scan_report(
        self,
        file_id: str,
        scan_report: Dict[str, Any],
        sha256_whole: str
    ) -> None:
        """
        Insert scan report record into database.
        
        Args:
            file_id: File identifier
            scan_report: Scan report dictionary
            sha256_whole: SHA256 hash
        """
        try:
            tool = scan_report.get('tool', 'unknown')
            tool_version = scan_report.get('toolVersion', 'unknown')
            scanned_at_str = scan_report.get('scannedAt')
            result = scan_report.get('result')
            
            # Parse scannedAt timestamp
            scanned_at = datetime.fromisoformat(scanned_at_str.replace('Z', '+00:00'))
            
            self.db.execute_update(
                """
                INSERT INTO scan_reports (
                    file_id, tool, tool_version, scanned_at, result, file_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (file_id, tool, tool_version, scanned_at, result, sha256_whole)
            )
            
            logger.debug(f"Scan report inserted for file {file_id}")
            
        except Exception as e:
            logger.error(f"Failed to insert scan report: {e}")
            # Don't fail the upload if scan report insert fails
    
    def handle_upload_complete(
        self,
        file_id: str,
        sha256_whole: str,
        stored_name: str,
        final_size: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Handle UPLOAD_COMPLETE message from Storage Node.
        
        Process:
        1. Update file status to 'READY' in PostgreSQL
        2. Broadcast NEW_FILE notification to room subscribers
        3. Write audit log entry
        
        Args:
            file_id: File identifier
            sha256_whole: SHA256 hash of assembled file
            stored_name: Storage path on Storage Node
            final_size: Final file size in bytes
        
        Returns:
            Tuple of (success, error_code)
        """
        try:
            # Get file details
            files = self.db.execute_query(
                """
                SELECT id, room_id, original_name, uploader_id, sha256_whole
                FROM files
                WHERE id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.warning(f"UPLOAD_COMPLETE failed: file {file_id} not found")
                return False, "FILE_NOT_FOUND"
            
            file = files[0]
            room_id = file['room_id']
            original_name = file['original_name']
            uploader_id = file['uploader_id']
            expected_hash = file['sha256_whole']
            
            # Verify hash matches (optional security check)
            if sha256_whole != expected_hash:
                logger.error(
                    f"UPLOAD_COMPLETE hash mismatch: file={file_id}, "
                    f"expected={expected_hash}, actual={sha256_whole}"
                )
                # Update to DELETED status due to hash mismatch
                self.db.execute_update(
                    "UPDATE files SET status = %s WHERE id = %s",
                    ('DELETED', file_id)
                )
                return False, "HASH_MISMATCH"
            
            # Update file status to READY
            self.db.execute_update(
                "UPDATE files SET status = %s WHERE id = %s",
                ('READY', file_id)
            )
            
            logger.info(
                f"Upload completed: file_id={file_id}, "
                f"name={original_name}, room={room_id}"
            )
            
            # Broadcast NEW_FILE notification
            if self.notification:
                self.notification.broadcast_new_file(
                    room_id=room_id,
                    file_id=file_id,
                    file_name=original_name,
                    uploader=uploader_id
                )
            
            # Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=uploader_id,
                    action='UPLOAD',
                    target_type='file',
                    target_id=file_id,
                    room_id=room_id,
                    detail={
                        'original_name': original_name,
                        'size_bytes': final_size,
                        'stored_name': stored_name
                    },
                    status='SUCCESS'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to handle upload complete: {e}")
            return False, "DATABASE_ERROR"
    
    def handle_upload_failed(
        self,
        file_id: str,
        reason: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Handle UPLOAD_FAILED message from Storage Node.
        
        Process:
        1. Update file status to 'DELETED'
        2. Write audit log entry
        
        Args:
            file_id: File identifier
            reason: Failure reason from Storage Node
        
        Returns:
            Tuple of (success, error_code)
        """
        try:
            # Get file details
            files = self.db.execute_query(
                """
                SELECT id, room_id, original_name, uploader_id
                FROM files
                WHERE id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.warning(f"UPLOAD_FAILED: file {file_id} not found")
                return False, "FILE_NOT_FOUND"
            
            file = files[0]
            room_id = file['room_id']
            original_name = file['original_name']
            uploader_id = file['uploader_id']
            
            # Update file status to DELETED
            self.db.execute_update(
                "UPDATE files SET status = %s WHERE id = %s",
                ('DELETED', file_id)
            )
            
            logger.warning(
                f"Upload failed: file_id={file_id}, "
                f"name={original_name}, reason={reason}"
            )
            
            # Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=uploader_id,
                    action='UPLOAD',
                    target_type='file',
                    target_id=file_id,
                    room_id=room_id,
                    detail={
                        'original_name': original_name,
                        'reason': reason
                    },
                    status='FAILED'
                )
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to handle upload failed: {e}")
            return False, "DATABASE_ERROR"
