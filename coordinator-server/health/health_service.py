"""Health check service for monitoring system status."""
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from database import Database
from redis_client import RedisClient
from logging_config import get_logger

logger = get_logger(__name__)


class HealthService:
    """
    Service for health check operations.
    
    Requirements: 13.1, 13.2, 13.3
    """
    
    def __init__(
        self,
        db: Database,
        redis_client: RedisClient,
        storage_node_server: Optional[Any] = None
    ):
        """
        Initialize health service.
        
        Args:
            db: Database instance
            redis_client: Redis client instance
            storage_node_server: Optional Storage Node server for status checks
        """
        self.db = db
        self.redis_client = redis_client
        self.storage_node_server = storage_node_server
        self.start_time = time.time()
        
        logger.info("HealthService initialized")
    
    def ping(self) -> Dict[str, Any]:
        """
        Handle PING request.
        
        Requirements: 13.1, 13.2
        
        Returns:
            Dictionary with pong and timestamp
        """
        return {
            "pong": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status.
        
        Requirements: 13.3
        
        Returns:
            Dictionary with connection status and uptime
        """
        # Calculate uptime
        uptime_seconds = int(time.time() - self.start_time)
        
        # Check PostgreSQL connection
        postgres_status = self._check_postgres()
        
        # Check Redis connection
        redis_status = self._check_redis()
        
        # Check Storage Node connections
        storage_node_status = self._check_storage_nodes()
        
        return {
            "uptime": uptime_seconds,
            "postgres": postgres_status,
            "redis": redis_status,
            "storageNodes": storage_node_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _check_postgres(self) -> Dict[str, Any]:
        """
        Check PostgreSQL connection status.
        
        Returns:
            Dictionary with status and optional error
        """
        try:
            # Execute simple query
            result = self.db.execute_query("SELECT 1 as test")
            
            if result and len(result) > 0 and result[0].get('test') == 1:
                return {
                    "status": "connected",
                    "healthy": True
                }
            else:
                return {
                    "status": "error",
                    "healthy": False,
                    "error": "Unexpected query result"
                }
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return {
                "status": "error",
                "healthy": False,
                "error": str(e)
            }
    
    def _check_redis(self) -> Dict[str, Any]:
        """
        Check Redis connection status.
        
        Returns:
            Dictionary with status and optional error
        """
        try:
            if self.redis_client.ping():
                return {
                    "status": "connected",
                    "healthy": True
                }
            else:
                return {
                    "status": "error",
                    "healthy": False,
                    "error": "Ping failed"
                }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "error",
                "healthy": False,
                "error": str(e)
            }
    
    def _check_storage_nodes(self) -> Dict[str, Any]:
        """
        Check Storage Node connection status.
        
        Returns:
            Dictionary with node count and status
        """
        if not self.storage_node_server:
            return {
                "status": "not_configured",
                "healthy": False,
                "connectedNodes": 0
            }
        
        try:
            connected_nodes = self.storage_node_server.get_connected_nodes()
            healthy_nodes = [node for node in connected_nodes if node.get('healthy', False)]
            
            return {
                "status": "connected" if len(healthy_nodes) > 0 else "no_healthy_nodes",
                "healthy": len(healthy_nodes) > 0,
                "connectedNodes": len(connected_nodes),
                "healthyNodes": len(healthy_nodes)
            }
        except Exception as e:
            logger.error(f"Storage Node health check failed: {e}")
            return {
                "status": "error",
                "healthy": False,
                "error": str(e),
                "connectedNodes": 0
            }
