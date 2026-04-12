"""Ticket service for generating and verifying upload/download tickets."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from redis_client import RedisClient
from logging_config import get_logger

logger = get_logger(__name__)


class TicketService:
    """
    Handles ticket generation and verification for upload/download authorization.
    
    Tickets are stored in Redis with TTL:
    - Upload tickets: 30 minutes (configurable)
    - Download tickets: 15 minutes (configurable)
    
    Storage Nodes verify tickets by calling the Coordinator via VERIFY_TICKET message.
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        upload_ticket_ttl_seconds: int = 1800,  # 30 minutes
        download_ticket_ttl_seconds: int = 900   # 15 minutes
    ):
        """
        Initialize ticket service.
        
        Args:
            redis_client: Redis client for ticket storage
            upload_ticket_ttl_seconds: Upload ticket TTL (default 30 minutes)
            download_ticket_ttl_seconds: Download ticket TTL (default 15 minutes)
        """
        self.redis = redis_client
        self.upload_ticket_ttl = upload_ticket_ttl_seconds
        self.download_ticket_ttl = download_ticket_ttl_seconds
    
    def generate_upload_ticket(
        self,
        file_id: str,
        user_id: str,
        room_id: str,
        total_chunks: int,
        chunk_size: int,
        sha256_whole: str,
        stored_name: str
    ) -> str:
        """
        Generate an upload ticket with 30-minute expiration.
        
        Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
        
        Args:
            file_id: File identifier
            user_id: User performing upload
            room_id: Room containing the file
            total_chunks: Number of chunks
            chunk_size: Size of each chunk in bytes
            sha256_whole: SHA256 hash of entire file
            stored_name: Storage path on Storage Node
        
        Returns:
            Ticket ID (UUID string)
        """
        # Generate unique ticket ID
        ticket_id = str(uuid.uuid4())
        
        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.upload_ticket_ttl)
        
        # Create ticket metadata
        ticket_data = {
            'type': 'upload',
            'fileId': file_id,
            'userId': user_id,
            'roomId': room_id,
            'totalChunks': total_chunks,
            'chunkSize': chunk_size,
            'sha256Whole': sha256_whole,
            'storedName': stored_name,
            'expiresAt': expires_at.isoformat()
        }
        
        # Store in Redis with TTL
        self.redis.set_ticket(ticket_id, ticket_data, self.upload_ticket_ttl)
        
        logger.info(
            f"Upload ticket generated: ticket={ticket_id}, "
            f"file={file_id}, ttl={self.upload_ticket_ttl}s"
        )
        
        return ticket_id
    
    def generate_download_ticket(
        self,
        file_id: str,
        stored_name: str,
        sha256_whole: str,
        total_chunks: int,
        chunk_size: int
    ) -> str:
        """
        Generate a download ticket with 15-minute expiration.
        
        Requirements: 6.1, 6.2, 6.4, 6.5
        
        Args:
            file_id: File identifier
            stored_name: Storage path on Storage Node
            sha256_whole: SHA256 hash of entire file
            total_chunks: Number of chunks
            chunk_size: Size of each chunk in bytes
        
        Returns:
            Ticket ID (UUID string)
        """
        # Generate unique ticket ID
        ticket_id = str(uuid.uuid4())
        
        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.download_ticket_ttl)
        
        # Create ticket metadata
        ticket_data = {
            'type': 'download',
            'fileId': file_id,
            'storedName': stored_name,
            'sha256Whole': sha256_whole,
            'totalChunks': total_chunks,
            'chunkSize': chunk_size,
            'expiresAt': expires_at.isoformat()
        }
        
        # Store in Redis with TTL
        self.redis.set_ticket(ticket_id, ticket_data, self.download_ticket_ttl)
        
        logger.info(
            f"Download ticket generated: ticket={ticket_id}, "
            f"file={file_id}, ttl={self.download_ticket_ttl}s"
        )
        
        return ticket_id
    
    def verify_ticket(self, ticket_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Verify a ticket and return its metadata.
        
        Called by Storage Node via VERIFY_TICKET message.
        
        Requirements: 6.6, 6.7, 6.8, 6.9
        
        Args:
            ticket_id: Ticket identifier
        
        Returns:
            Tuple of (is_valid, ticket_metadata, error_code)
            - is_valid: True if ticket exists and not expired
            - ticket_metadata: Ticket data if valid, None otherwise
            - error_code: Error code if invalid, None otherwise
        """
        try:
            # Retrieve ticket from Redis
            ticket_data = self.redis.get_ticket(ticket_id)
            
            if not ticket_data:
                logger.info(f"Ticket verification failed: ticket {ticket_id} not found")
                return False, None, "TICKET_NOT_FOUND"
            
            # Check expiration
            expires_at_str = ticket_data.get('expiresAt')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at <= datetime.now(timezone.utc):
                    logger.info(f"Ticket verification failed: ticket {ticket_id} expired")
                    # Clean up expired ticket
                    self.redis.delete_ticket(ticket_id)
                    return False, None, "TICKET_EXPIRED"
            
            logger.info(f"Ticket verified: ticket={ticket_id}, type={ticket_data.get('type')}")
            
            return True, ticket_data, None
            
        except Exception as e:
            logger.error(f"Failed to verify ticket {ticket_id}: {e}")
            return False, None, "INTERNAL_ERROR"
    
    def delete_ticket(self, ticket_id: str) -> bool:
        """
        Manually delete a ticket (optional cleanup for consumed tickets).
        
        Requirements: 6.10
        
        Note: Redis TTL handles automatic expiration, but this method
        allows manual cleanup when a ticket is consumed.
        
        Args:
            ticket_id: Ticket identifier
        
        Returns:
            True if ticket was deleted, False if not found
        """
        try:
            deleted = self.redis.delete_ticket(ticket_id)
            
            if deleted:
                logger.debug(f"Ticket manually deleted: {ticket_id}")
            else:
                logger.debug(f"Ticket not found for deletion: {ticket_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete ticket {ticket_id}: {e}")
            return False
