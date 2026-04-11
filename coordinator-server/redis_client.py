"""Redis client for session storage and ticket management."""
import redis
import json
from typing import Optional, Any, Dict
from config import RedisConfig
from logging_config import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Redis client wrapper for session and ticket storage."""
    
    def __init__(self, config: RedisConfig):
        """
        Initialize Redis client.
        
        Args:
            config: Redis configuration
        """
        self.config = config
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
    
    def connect(self) -> None:
        """Create Redis connection pool and client."""
        try:
            self._pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password if self.config.password else None,
                max_connections=self.config.pool_size,
                decode_responses=True
            )
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            self._client.ping()
            logger.info(f"Redis connection established (host={self.config.host}:{self.config.port})")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            logger.info("Redis connection closed")
    
    def set_session(self, token: str, user_data: Dict[str, Any], ttl_seconds: int) -> None:
        """
        Store session data in Redis.
        
        Args:
            token: Session token (UUID)
            user_data: User session data (userId, globalRole, createdAt)
            ttl_seconds: Time to live in seconds
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"session:{token}"
        value = json.dumps(user_data)
        self._client.setex(key, ttl_seconds, value)
        logger.debug(f"Session stored: {key} (TTL={ttl_seconds}s)")
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from Redis.
        
        Args:
            token: Session token
        
        Returns:
            Session data dictionary or None if not found
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"session:{token}"
        value = self._client.get(key)
        
        if value:
            return json.loads(value)
        return None
    
    def delete_session(self, token: str) -> bool:
        """
        Delete session from Redis.
        
        Args:
            token: Session token
        
        Returns:
            True if session was deleted, False if not found
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"session:{token}"
        result = self._client.delete(key)
        logger.debug(f"Session deleted: {key}")
        return result > 0
    
    def set_ticket(self, ticket_id: str, ticket_data: Dict[str, Any], ttl_seconds: int) -> None:
        """
        Store ticket data in Redis.
        
        Args:
            ticket_id: Ticket identifier
            ticket_data: Ticket metadata
            ttl_seconds: Time to live in seconds
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"ticket:{ticket_id}"
        value = json.dumps(ticket_data)
        self._client.setex(key, ttl_seconds, value)
        logger.debug(f"Ticket stored: {key} (TTL={ttl_seconds}s)")
    
    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve ticket data from Redis.
        
        Args:
            ticket_id: Ticket identifier
        
        Returns:
            Ticket data dictionary or None if not found
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"ticket:{ticket_id}"
        value = self._client.get(key)
        
        if value:
            return json.loads(value)
        return None
    
    def delete_ticket(self, ticket_id: str) -> bool:
        """
        Delete ticket from Redis.
        
        Args:
            ticket_id: Ticket identifier
        
        Returns:
            True if ticket was deleted, False if not found
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized. Call connect() first.")
        
        key = f"ticket:{ticket_id}"
        result = self._client.delete(key)
        logger.debug(f"Ticket deleted: {key}")
        return result > 0
    
    def ping(self) -> bool:
        """
        Test Redis connection.
        
        Returns:
            True if connection is alive
        """
        if not self._client:
            return False
        
        try:
            return self._client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False
