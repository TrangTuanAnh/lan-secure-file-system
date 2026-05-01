"""Download control service for file download management."""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from database import Database
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from redis_client import RedisClient
from ticket.hmac_ticket import create_hmac_ticket_fields
from logging_config import get_logger

logger = get_logger(__name__)


class DownloadService:
    """Handles file download control plane operations."""
    
    def __init__(
        self,
        database: Database,
        redis_client: RedisClient,
        authorization_service: AuthorizationService,
        audit_service: Optional[AuditService] = None,
        ticket_ttl_seconds: int = 900,  # 15 minutes default
        storage_address: str = "localhost:9000",  # Default storage node address
        storage_registry: Optional[Any] = None,
        ticket_secret: str = "default_secret",
        default_storage_node_id: str = "node-1"
    ):
        """
        Initialize download service.
        
        Args:
            database: Database instance
            redis_client: Redis client for ticket storage
            authorization_service: Authorization service for permission checks
            audit_service: Optional audit service for logging
            ticket_ttl_seconds: Ticket expiration time in seconds (default 15 minutes)
            storage_address: Storage node address (host:port)
            storage_registry: Optional registry for resolving owning nodes
            ticket_secret: Shared secret used for data-plane HMAC ticket fields
            default_storage_node_id: Legacy node ID used when no owner is recorded
        """
        self.db = database
        self.redis = redis_client
        self.authz = authorization_service
        self.audit = audit_service
        self.ticket_ttl_seconds = ticket_ttl_seconds
        self.storage_address = storage_address
        self.storage_registry = storage_registry
        self.ticket_secret = ticket_secret
        self.default_storage_node_id = default_storage_node_id

    def _resolve_storage_node(
        self,
        file: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        node_id = file.get('storage_node_id')
        if node_id and self.storage_registry:
            address = self.storage_registry.get_storage_address(node_id)
            if not address:
                return None, node_id, "STORAGE_NODE_UNAVAILABLE"
            return address, node_id, None
        return self.storage_address, node_id, None

    def _ticket_fields(self, file_id: str, node_id: Optional[str]) -> Dict[str, Any]:
        return create_hmac_ticket_fields(
            file_id=file_id,
            node_id=node_id or self.default_storage_node_id,
            secret=self.ticket_secret,
            ttl_seconds=self.ticket_ttl_seconds
        )
    
    def handle_init_download_direct(
        self,
        user_id: str,
        global_role: str,
        file_id: str,
        version: Optional[int] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Handle INIT_DOWNLOAD request with direct permission (access token).
        
        Process:
        1. Verify user is member of file's room or ADMIN
        2. Select file version (highest if not specified)
        3. Generate download ticket with 15-minute expiration
        4. Store ticket metadata in Redis
        5. Return DOWNLOAD_PLAN
        6. Write audit log entry
        
        Args:
            user_id: User initiating download
            global_role: User's global role
            file_id: File identifier
            version: Optional specific version number
        
        Returns:
            Tuple of (success, download_plan, error_code)
            download_plan contains:
                - ticket: Download ticket
                - storageAddress: Storage node address
                - fileName: Original filename
                - fileSize: File size in bytes
                - sha256Whole: SHA256 hash
                - totalChunks: Number of chunks
                - chunkSize: Chunk size in bytes
        """
        try:
            # Get file details
            if version is not None:
                # Get specific version
                files = self.db.execute_query(
                    """
                    SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                           f.size_bytes, f.sha256_whole, f.total_chunks, f.chunk_size,
                           f.status, f.storage_node_id
                    FROM files f
                    WHERE f.id = %s AND f.version = %s
                    """,
                    (file_id, version)
                )
            else:
                # Get file by ID (should be latest version if queried by ID)
                files = self.db.execute_query(
                    """
                    SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                           f.size_bytes, f.sha256_whole, f.total_chunks, f.chunk_size,
                           f.status, f.storage_node_id
                    FROM files f
                    WHERE f.id = %s
                    """,
                    (file_id,)
                )
            
            if not files:
                logger.info(f"INIT_DOWNLOAD failed: file {file_id} not found")
                return False, None, "FILE_NOT_FOUND"
            
            file = files[0]
            
            # Check file status
            if file['status'] != 'READY':
                logger.info(f"INIT_DOWNLOAD failed: file {file_id} status is {file['status']}")
                return False, None, "FILE_NOT_READY"
            
            room_id = file['room_id']
            
            # Step 1: Verify user is member of file's room or ADMIN
            if not self.authz.check_permission(user_id, global_role, room_id, 'DOWNLOAD_FILE'):
                logger.info(f"INIT_DOWNLOAD denied: user {user_id} lacks permission for file {file_id}")
                return False, None, "PERMISSION_DENIED"

            storage_address, storage_node_id, resolve_error = self._resolve_storage_node(file)
            if resolve_error:
                logger.warning(
                    f"INIT_DOWNLOAD failed: storage node unavailable for file={file_id}, "
                    f"storage_node_id={storage_node_id}"
                )
                return False, None, resolve_error
            
            # Step 3: Generate download ticket
            ticket = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ticket_ttl_seconds)
            data_plane_ticket = self._ticket_fields(file['id'], storage_node_id)
            
            # Step 4: Store ticket metadata in Redis
            ticket_data = {
                'type': 'download',
                'fileId': file['id'],
                'storedName': file['stored_name'],
                'sha256Whole': file['sha256_whole'],
                'totalChunks': file['total_chunks'],
                'chunkSize': file['chunk_size'],
                'storageNodeId': storage_node_id,
                'storageAddress': storage_address,
                **data_plane_ticket,
                'expiresAt': expires_at.isoformat()
            }
            
            self.redis.set_ticket(ticket, ticket_data, self.ticket_ttl_seconds)
            
            logger.info(
                f"Download initialized: file_id={file_id}, "
                f"ticket={ticket}, user={user_id}"
            )
            
            # Step 5: Return DOWNLOAD_PLAN
            download_plan = {
                'ticket': ticket,
                'storageAddress': storage_address,
                'storageNodeId': storage_node_id,
                'fileName': file['original_name'],
                'fileSize': file['size_bytes'],
                'sha256Whole': file['sha256_whole'],
                'totalChunks': file['total_chunks'],
                'chunkSize': file['chunk_size'],
                **data_plane_ticket
            }
            
            # Step 6: Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='DOWNLOAD',
                    target_type='file',
                    target_id=file_id,
                    room_id=room_id,
                    detail={
                        'original_name': file['original_name'],
                        'version': file['version'],
                        'method': 'direct'
                    },
                    status='SUCCESS'
                )
            
            return True, download_plan, None
            
        except Exception as e:
            logger.error(f"Failed to initialize download: {e}")
            return False, None, "DATABASE_ERROR"
    
    def create_share_token(
        self,
        user_id: str,
        global_role: str,
        file_id: str,
        max_downloads: int,
        expires_at: datetime
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a share token for a file.
        
        Process:
        1. Verify user is ADMIN, OWNER, or MEMBER of file's room
        2. Generate 32 random bytes and encode as hexadecimal
        3. Insert record into share_tokens table
        4. Return token string
        5. Write audit log entry
        
        Args:
            user_id: User creating the share token
            global_role: User's global role
            file_id: File identifier
            max_downloads: Maximum number of downloads allowed
            expires_at: Token expiration timestamp
        
        Returns:
            Tuple of (success, token_string, error_code)
        """
        try:
            # Get file details to check room membership
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name
                FROM files f
                WHERE f.id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.info(f"CREATE_SHARE_TOKEN failed: file {file_id} not found")
                return False, None, "FILE_NOT_FOUND"
            
            file = files[0]
            room_id = file['room_id']
            
            # Step 1: Verify user is ADMIN, OWNER, or MEMBER of file's room
            if not self.authz.check_permission(user_id, global_role, room_id, 'CREATE_SHARE_TOKEN'):
                logger.info(f"CREATE_SHARE_TOKEN denied: user {user_id} lacks permission for file {file_id}")
                return False, None, "PERMISSION_DENIED"
            
            # Step 2: Generate 32 random bytes and encode as hexadecimal
            token_bytes = secrets.token_bytes(32)
            token_string = token_bytes.hex()
            
            # Step 3: Insert record into share_tokens table
            token_id = str(uuid.uuid4())
            
            self.db.execute_update(
                """
                INSERT INTO share_tokens (
                    id, token, file_id, created_by, max_downloads, download_count, expires_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    token_id, token_string, file_id, user_id,
                    max_downloads, 0, expires_at, datetime.now(timezone.utc)
                )
            )
            
            logger.info(
                f"Share token created: token_id={token_id}, "
                f"file_id={file_id}, max_downloads={max_downloads}"
            )
            
            # Step 5: Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='CREATE_SHARE_TOKEN',
                    target_type='share_token',
                    target_id=token_id,
                    room_id=room_id,
                    detail={
                        'file_id': file_id,
                        'original_name': file['original_name'],
                        'max_downloads': max_downloads,
                        'expires_at': expires_at.isoformat()
                    },
                    status='SUCCESS'
                )
            
            # Step 4: Return token string
            return True, token_string, None
            
        except Exception as e:
            logger.error(f"Failed to create share token: {e}")
            return False, None, "DATABASE_ERROR"
    
    def handle_init_download_share(
        self,
        share_token: str,
        file_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Handle INIT_DOWNLOAD request with share token (no access token required).
        
        Process:
        1. Execute atomic UPDATE on share_tokens incrementing download_count
        2. Verify download_count < max_downloads and expires_at > NOW()
        3. Return error if validation fails
        4. Generate download ticket
        5. Return DOWNLOAD_PLAN
        6. Write audit log entry
        
        Args:
            share_token: Share token string
            file_id: File identifier
        
        Returns:
            Tuple of (success, download_plan, error_code)
        """
        try:
            # Step 1 & 2: Atomic UPDATE with validation
            # This ensures thread-safe increment and validation in a single query
            result = self.db.execute_query(
                """
                UPDATE share_tokens
                SET download_count = download_count + 1
                WHERE token = %s
                  AND file_id = %s
                  AND download_count < max_downloads
                  AND expires_at > NOW()
                RETURNING id, file_id, created_by, download_count, max_downloads, expires_at
                """,
                (share_token, file_id)
            )
            
            # Step 3: Check if update succeeded
            if not result:
                # Token validation failed - determine specific error
                # Query to check why it failed
                token_check = self.db.execute_query(
                    """
                    SELECT id, file_id, download_count, max_downloads, expires_at
                    FROM share_tokens
                    WHERE token = %s
                    """,
                    (share_token,)
                )
                
                if not token_check:
                    logger.info(f"INIT_DOWNLOAD with share token failed: token not found")
                    return False, None, "INVALID_SHARE_TOKEN"
                
                token_data = token_check[0]
                
                # Check if file_id matches
                if token_data['file_id'] != file_id:
                    logger.info(f"INIT_DOWNLOAD with share token failed: file_id mismatch")
                    return False, None, "INVALID_SHARE_TOKEN"
                
                # Check if expired
                if token_data['expires_at'] <= datetime.now(timezone.utc):
                    logger.info(f"INIT_DOWNLOAD with share token failed: token expired")
                    return False, None, "SHARE_TOKEN_EXPIRED"
                
                # Check if exhausted
                if token_data['download_count'] >= token_data['max_downloads']:
                    logger.info(f"INIT_DOWNLOAD with share token failed: token exhausted")
                    return False, None, "SHARE_TOKEN_EXHAUSTED"
                
                # Unknown error
                logger.warning(f"INIT_DOWNLOAD with share token failed: unknown reason")
                return False, None, "INVALID_SHARE_TOKEN"
            
            token_data = result[0]
            
            # Get file details
            files = self.db.execute_query(
                """
                SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                       f.size_bytes, f.sha256_whole, f.total_chunks, f.chunk_size,
                       f.status, f.storage_node_id
                FROM files f
                WHERE f.id = %s
                """,
                (file_id,)
            )
            
            if not files:
                logger.error(f"INIT_DOWNLOAD with share token: file {file_id} not found after token validation")
                return False, None, "FILE_NOT_FOUND"
            
            file = files[0]
            
            # Check file status
            if file['status'] != 'READY':
                logger.info(f"INIT_DOWNLOAD with share token failed: file {file_id} status is {file['status']}")
                return False, None, "FILE_NOT_READY"

            storage_address, storage_node_id, resolve_error = self._resolve_storage_node(file)
            if resolve_error:
                logger.warning(
                    f"INIT_DOWNLOAD with share token failed: storage node unavailable "
                    f"for file={file_id}, storage_node_id={storage_node_id}"
                )
                return False, None, resolve_error
            
            # Step 4: Generate download ticket
            ticket = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ticket_ttl_seconds)
            data_plane_ticket = self._ticket_fields(file['id'], storage_node_id)
            
            ticket_data = {
                'type': 'download',
                'fileId': file['id'],
                'storedName': file['stored_name'],
                'sha256Whole': file['sha256_whole'],
                'totalChunks': file['total_chunks'],
                'chunkSize': file['chunk_size'],
                'storageNodeId': storage_node_id,
                'storageAddress': storage_address,
                **data_plane_ticket,
                'expiresAt': expires_at.isoformat()
            }
            
            self.redis.set_ticket(ticket, ticket_data, self.ticket_ttl_seconds)
            
            logger.info(
                f"Download initialized with share token: file_id={file_id}, "
                f"ticket={ticket}, download_count={token_data['download_count']}/{token_data['max_downloads']}"
            )
            
            # Step 5: Return DOWNLOAD_PLAN
            download_plan = {
                'ticket': ticket,
                'storageAddress': storage_address,
                'storageNodeId': storage_node_id,
                'fileName': file['original_name'],
                'fileSize': file['size_bytes'],
                'sha256Whole': file['sha256_whole'],
                'totalChunks': file['total_chunks'],
                'chunkSize': file['chunk_size'],
                **data_plane_ticket
            }
            
            # Step 6: Write audit log entry
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=token_data['created_by'],  # Token creator, not downloader
                    action='USE_SHARE_TOKEN',
                    target_type='share_token',
                    target_id=token_data['id'],
                    room_id=file['room_id'],
                    detail={
                        'file_id': file_id,
                        'original_name': file['original_name'],
                        'download_count': token_data['download_count'],
                        'max_downloads': token_data['max_downloads']
                    },
                    status='SUCCESS'
                )
            
            return True, download_plan, None
            
        except Exception as e:
            logger.error(f"Failed to initialize download with share token: {e}")
            return False, None, "DATABASE_ERROR"
    
    def select_file_version(
        self,
        room_id: str,
        original_name: str,
        version: Optional[int] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Select a specific file version or the latest version.
        
        Args:
            room_id: Room identifier
            original_name: Original filename
            version: Optional specific version number (None for latest)
        
        Returns:
            Tuple of (success, file_data, error_code)
        """
        try:
            if version is not None:
                # Get specific version
                files = self.db.execute_query(
                    """
                    SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                           f.size_bytes, f.sha256_whole, f.total_chunks, f.chunk_size,
                           f.status, f.storage_node_id
                    FROM files f
                    WHERE f.room_id = %s AND f.original_name = %s AND f.version = %s
                    """,
                    (room_id, original_name, version)
                )
            else:
                # Get latest version (highest version number)
                files = self.db.execute_query(
                    """
                    SELECT f.id, f.room_id, f.original_name, f.stored_name, f.version,
                           f.size_bytes, f.sha256_whole, f.total_chunks, f.chunk_size,
                           f.status, f.storage_node_id
                    FROM files f
                    WHERE f.room_id = %s AND f.original_name = %s
                    ORDER BY f.version DESC
                    LIMIT 1
                    """,
                    (room_id, original_name)
                )
            
            if not files:
                return False, None, "FILE_NOT_FOUND"
            
            return True, files[0], None
            
        except Exception as e:
            logger.error(f"Failed to select file version: {e}")
            return False, None, "DATABASE_ERROR"
