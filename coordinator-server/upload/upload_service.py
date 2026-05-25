"""Upload control service for file upload management."""
import uuid
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from database import Database
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from redis_client import RedisClient
from ticket.hmac_ticket import create_hmac_ticket_fields
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
        ticket_ttl_seconds: int = 1800,  # 30 minutes default
        storage_registry: Optional[Any] = None,
        storage_address: str = "localhost:9000",
        ticket_secret: str = "default_secret",
        default_storage_node_id: str = "node-1"
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
            storage_registry: Optional registry for connected Storage Nodes
            storage_address: Legacy fallback Storage Node address
            ticket_secret: Shared secret used for data-plane HMAC ticket fields
            default_storage_node_id: Legacy node ID used when no registry is configured
        """
        self.db = database
        self.redis = redis_client
        self.authz = authorization_service
        self.audit = audit_service
        self.notification = notification_service
        self.chunk_size = chunk_size
        self.ticket_ttl_seconds = ticket_ttl_seconds
        self.storage_registry = storage_registry
        self.storage_address = storage_address
        self.ticket_secret = ticket_secret
        self.default_storage_node_id = default_storage_node_id
        
        # Initialize validators and checkers
        self.dedup_checker = DeduplicationChecker(database)

    def _legacy_node(self, storage_address: Optional[str]) -> Dict[str, Any]:
        address = storage_address or self.storage_address
        return {
            'node_id': self.default_storage_node_id,
            'storage_address': address
        }

    def _select_storage_node(self, storage_address: Optional[str]) -> Optional[Dict[str, Any]]:
        if not self.storage_registry:
            return self._legacy_node(storage_address)

        node = self.storage_registry.select_for_upload()
        if not node:
            return None

        return {
            'node_id': node.node_id,
            'storage_address': node.storage_address
        }

    def _is_reusable_dedup_node(self, node_id: Optional[str]) -> bool:
        if not node_id:
            return True
        if not self.storage_registry:
            return True
        return self.storage_registry.is_node_healthy(node_id)

    def _dedup_storage_address(
        self,
        node_id: Optional[str],
        storage_address: Optional[str]
    ) -> Optional[str]:
        if node_id and self.storage_registry:
            return self.storage_registry.get_storage_address(node_id)
        return storage_address or self.storage_address

    def _pick_reusable_dedup(
        self,
        candidates: list[Dict[str, Any]],
        storage_address: Optional[str]
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        for candidate in candidates:
            node_id = candidate.get('storage_node_id')
            if not self._is_reusable_dedup_node(node_id):
                continue
            address = self._dedup_storage_address(node_id, storage_address)
            if address:
                return candidate, address
        return None, None

    def _ticket_fields(self, file_id: str, node_id: Optional[str]) -> Dict[str, Any]:
        return create_hmac_ticket_fields(
            file_id=file_id,
            node_id=node_id or self.default_storage_node_id,
            secret=self.ticket_secret,
            ttl_seconds=self.ticket_ttl_seconds
        )

    def _mark_upload_started(self, node_id: Optional[str]) -> None:
        if self.storage_registry and node_id:
            self.storage_registry.mark_upload_started(node_id)

    def _mark_upload_finished(self, node_id: Optional[str]) -> None:
        if self.storage_registry and node_id:
            self.storage_registry.mark_upload_finished(node_id)
    
    def handle_init_upload(
        self,
        user_id: str,
        global_role: str,
        room_id: str,
        file_info: Dict[str, Any],
        scan_report: Optional[Dict[str, Any]] = None,
        storage_address: str = "localhost:9000"  # Default storage node address
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Handle INIT_UPLOAD request.
        
        Process:
        1. Verify user has ADMIN, OWNER, or MEMBER role in room
        2. Check for deduplication
        3. If deduplicated: create file record with status READY, return deduplicated=true
        4. If not deduplicated: create file record with status UPLOADING, generate ticket
        
        Args:
            user_id: User initiating upload
            global_role: User's global role
            room_id: Target room ID
            file_info: File information dictionary with:
                - originalName: Original filename
                - sizeBytes: File size in bytes
                - mimeType: MIME type
                - sha256Whole: SHA256 hash of entire file
            scan_report: Deprecated client-side scan report. Ignored; storage nodes scan on finalize.
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
        
        # Step 2: Check for deduplication. Antivirus enforcement happens on the storage node
        # during FINALIZE_UPLOAD, before the object is committed to permanent storage.
        dedup_candidates = self.dedup_checker.find_deduplication_candidates(sha256_whole)
        existing_file, dedup_storage_address = self._pick_reusable_dedup(
            dedup_candidates,
            storage_address
        )
        
        # Calculate version number
        version = self._calculate_next_version(room_id, original_name)
        
        # Calculate total chunks
        total_chunks = math.ceil(size_bytes / self.chunk_size) if size_bytes > 0 else 1
        
        try:
            if existing_file:
                # Step 4: Deduplicated upload - create file record with status READY
                file_id = str(uuid.uuid4())
                stored_name = existing_file['stored_name']
                storage_node_id = existing_file.get('storage_node_id')
                
                # Insert file record
                self.db.execute_update(
                    """
                    INSERT INTO files (
                        id, room_id, original_name, stored_name, version,
                        uploader_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, chunk_size, status, storage_node_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id, room_id, original_name, stored_name, version,
                        user_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, self.chunk_size, 'READY', storage_node_id,
                        datetime.now(timezone.utc)
                    )
                )
                
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
                            'deduplicated': True,
                            'storage_node_id': storage_node_id
                        },
                        status='SUCCESS'
                    )
                
                # Return upload plan with deduplicated flag
                return True, {
                    'fileId': file_id,
                    'storageAddress': dedup_storage_address,
                    'storageNodeId': storage_node_id,
                    'chunkSize': self.chunk_size,
                    'totalChunks': total_chunks,
                    'deduplicated': True
                }, None
            
            else:
                # Step 5: New upload - create file record with status UPLOADING
                selected_node = self._select_storage_node(storage_address)
                if not selected_node:
                    logger.warning("INIT_UPLOAD failed: no healthy storage node available")
                    return False, None, "STORAGE_NODE_UNAVAILABLE"

                storage_node_id = selected_node['node_id']
                selected_storage_address = selected_node['storage_address']
                file_id = str(uuid.uuid4())
                stored_name = f"{room_id}/{file_id}"
                
                # Insert file record with UPLOADING status
                self.db.execute_update(
                    """
                    INSERT INTO files (
                        id, room_id, original_name, stored_name, version,
                        uploader_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, chunk_size, status, storage_node_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id, room_id, original_name, stored_name, version,
                        user_id, size_bytes, mime_type, sha256_whole,
                        total_chunks, self.chunk_size, 'UPLOADING', storage_node_id,
                        datetime.now(timezone.utc)
                    )
                )
                
                # Generate upload ticket
                ticket = str(uuid.uuid4())
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ticket_ttl_seconds)
                
                # Store ticket metadata in Redis
                data_plane_ticket = self._ticket_fields(file_id, storage_node_id)
                ticket_data = {
                    'type': 'upload',
                    'fileId': file_id,
                    'userId': user_id,
                    'roomId': room_id,
                    'totalChunks': total_chunks,
                    'chunkSize': self.chunk_size,
                    'sha256Whole': sha256_whole,
                    'storedName': stored_name,
                    'storageNodeId': storage_node_id,
                    'storageAddress': selected_storage_address,
                    **data_plane_ticket,
                    'expiresAt': expires_at.isoformat()
                }
                
                self.redis.set_ticket(ticket, ticket_data, self.ticket_ttl_seconds)
                self._mark_upload_started(storage_node_id)
                
                logger.info(
                    f"New upload initialized: file_id={file_id}, "
                    f"ticket={ticket}, room={room_id}, chunks={total_chunks}, "
                    f"storage_node={storage_node_id}"
                )
                
                # Return upload plan with ticket
                return True, {
                    'fileId': file_id,
                    'ticket': ticket,
                    'storageAddress': selected_storage_address,
                    'storageNodeId': storage_node_id,
                    'chunkSize': self.chunk_size,
                    'totalChunks': total_chunks,
                    'deduplicated': False,
                    **data_plane_ticket
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
    
    def handle_upload_complete(
        self,
        file_id: str,
        sha256_whole: str,
        stored_name: str,
        final_size: int,
        storage_node_id: Optional[str] = None
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
            storage_node_id: Storage Node reporting the completion
        
        Returns:
            Tuple of (success, error_code)
        """
        try:
            # Get file details
            files = self.db.execute_query(
                """
                SELECT id, room_id, original_name, uploader_id, sha256_whole, storage_node_id
                FROM files
                WHERE id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.warning(f"UPLOAD_COMPLETE failed: file {file_id} not found")
                self._mark_upload_finished(storage_node_id)
                # BUGFIX M10: audit log even when file row is missing — admin
                # needs visibility on storage-node ↔ DB drift.
                if self.audit:
                    self.audit.write_audit_log(
                        actor_id=None,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=None,
                        detail={
                            'reason': 'FILE_NOT_FOUND',
                            'reporter_node_id': storage_node_id,
                            'sha256_whole': sha256_whole,
                        },
                        status='FAILED'
                    )
                return False, "FILE_NOT_FOUND"

            file = files[0]
            room_id = file['room_id']
            original_name = file['original_name']
            uploader_id = file['uploader_id']
            expected_hash = file['sha256_whole']
            assigned_node_id = file.get('storage_node_id')

            self._mark_upload_finished(assigned_node_id or storage_node_id)

            if assigned_node_id and storage_node_id and assigned_node_id != storage_node_id:
                logger.warning(
                    f"UPLOAD_COMPLETE node mismatch: file={file_id}, "
                    f"assigned={assigned_node_id}, reporter={storage_node_id}"
                )
                # BUGFIX M9: mark the file FAILED so it doesn't sit in UPLOADING
                # until the orphan-cleanup window runs. Also audit log so the
                # discrepancy is investigable.
                try:
                    self.db.execute_update(
                        "UPDATE files SET status = %s WHERE id = %s AND status = %s",
                        ('DELETED', file_id, 'UPLOADING')
                    )
                except Exception as e:
                    logger.error(f"Failed to mark mismatched upload DELETED: {e}")
                if self.audit:
                    self.audit.write_audit_log(
                        actor_id=uploader_id,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=room_id,
                        detail={
                            'original_name': original_name,
                            'reason': 'STORAGE_NODE_MISMATCH',
                            'assigned_node_id': assigned_node_id,
                            'reporter_node_id': storage_node_id,
                        },
                        status='FAILED'
                    )
                return False, "STORAGE_NODE_MISMATCH"

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
                # BUGFIX M10: write audit log + broadcast FILE_DELETED so admin
                # AND clients in the room are informed.
                if self.audit:
                    self.audit.write_audit_log(
                        actor_id=uploader_id,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=room_id,
                        detail={
                            'original_name': original_name,
                            'reason': 'HASH_MISMATCH',
                            'expected_sha256': expected_hash,
                            'actual_sha256': sha256_whole,
                            'storage_node_id': assigned_node_id,
                        },
                        status='FAILED'
                    )
                if self.notification:
                    try:
                        self.notification.broadcast_file_deleted(
                            room_id=room_id,
                            file_id=file_id,
                            file_name=original_name,
                            deleted_by='system'
                        )
                    except Exception as e:
                        logger.error(f"Failed to broadcast FILE_DELETED: {e}")
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
                        'stored_name': stored_name,
                        'storage_node_id': assigned_node_id
                    },
                    status='SUCCESS'
                )
            
            return True, None

        except Exception as e:
            logger.error(f"Failed to handle upload complete: {e}", exc_info=True)
            # BUGFIX M10: audit log even on unexpected error so failures aren't silent.
            if self.audit:
                try:
                    self.audit.write_audit_log(
                        actor_id=None,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=None,
                        detail={
                            'reason': 'DATABASE_ERROR',
                            'error_type': e.__class__.__name__,
                            'reporter_node_id': storage_node_id,
                        },
                        status='FAILED'
                    )
                except Exception:
                    pass
            return False, "DATABASE_ERROR"

    def handle_upload_failed(
        self,
        file_id: str,
        reason: str,
        storage_node_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Handle UPLOAD_FAILED message from Storage Node.

        Process:
            1. Lookup file metadata
            2. Mark the file as DELETED
            3. Audit log + broadcast FILE_DELETED to room subscribers

        Args:
            file_id: File identifier
            reason: Failure reason from Storage Node
            storage_node_id: Storage Node reporting the failure

        Returns:
            (success, error_code)
        """
        try:
            files = self.db.execute_query(
                """
                SELECT id, room_id, original_name, uploader_id, storage_node_id
                FROM files
                WHERE id = %s
                """,
                (file_id,)
            )

            if not files:
                logger.warning(f"UPLOAD_FAILED: file {file_id} not found")
                self._mark_upload_finished(storage_node_id)
                if self.audit:
                    try:
                        self.audit.write_audit_log(
                            actor_id=None,
                            action='UPLOAD',
                            target_type='file',
                            target_id=file_id,
                            room_id=None,
                            detail={
                                'reason': 'FILE_NOT_FOUND',
                                'original_failure_reason': reason,
                                'reporter_node_id': storage_node_id,
                            },
                            status='FAILED'
                        )
                    except Exception:
                        pass
                return False, "FILE_NOT_FOUND"

            file = files[0]
            room_id = file['room_id']
            original_name = file['original_name']
            uploader_id = file['uploader_id']
            assigned_node_id = file.get('storage_node_id')

            self._mark_upload_finished(assigned_node_id or storage_node_id)

            if assigned_node_id and storage_node_id and assigned_node_id != storage_node_id:
                logger.warning(
                    f"UPLOAD_FAILED node mismatch: file={file_id}, "
                    f"assigned={assigned_node_id}, reporter={storage_node_id}"
                )
                if self.audit:
                    try:
                        self.audit.write_audit_log(
                            actor_id=uploader_id,
                            action='UPLOAD',
                            target_type='file',
                            target_id=file_id,
                            room_id=room_id,
                            detail={
                                'reason': 'STORAGE_NODE_MISMATCH',
                                'original_failure_reason': reason,
                                'assigned_node_id': assigned_node_id,
                                'reporter_node_id': storage_node_id,
                            },
                            status='FAILED'
                        )
                    except Exception:
                        pass
                return False, "STORAGE_NODE_MISMATCH"

            # Mark DELETED
            self.db.execute_update(
                "UPDATE files SET status = %s WHERE id = %s",
                ('DELETED', file_id)
            )

            logger.warning(
                f"Upload failed: file_id={file_id}, "
                f"name={original_name}, reason={reason}"
            )

            # Audit log
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=uploader_id,
                    action='UPLOAD',
                    target_type='file',
                    target_id=file_id,
                    room_id=room_id,
                    detail={
                        'original_name': original_name,
                        'reason': reason,
                        'storage_node_id': assigned_node_id,
                    },
                    status='FAILED'
                )

            # BUGFIX M10: broadcast FILE_DELETED so clients in the room don't
            # see a phantom UPLOADING entry forever.
            if self.notification:
                try:
                    self.notification.broadcast_file_deleted(
                        room_id=room_id,
                        file_id=file_id,
                        file_name=original_name,
                        deleted_by='system'
                    )
                except Exception as e:
                    logger.error(f"Failed to broadcast FILE_DELETED: {e}")

            return True, None

        except Exception as e:
            logger.error(f"Failed to handle upload failed: {e}", exc_info=True)
            if self.audit:
                try:
                    self.audit.write_audit_log(
                        actor_id=None,
                        action='UPLOAD',
                        target_type='file',
                        target_id=file_id,
                        room_id=None,
                        detail={
                            'reason': 'DATABASE_ERROR_DURING_FAIL_HANDLING',
                            'error_type': e.__class__.__name__,
                            'original_failure_reason': reason,
                            'reporter_node_id': storage_node_id,
                        },
                        status='FAILED'
                    )
                except Exception:
                    pass
            return False, "DATABASE_ERROR"
