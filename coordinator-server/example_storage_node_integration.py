"""
Example integration for Storage Node communication server.

This example demonstrates how to:
1. Initialize the Storage Node server
2. Start listening for Storage Node connections
3. Handle authentication, heartbeat, and upload notifications

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
"""
import time
from config import load_config
from database import Database
from redis_client import RedisClient
from ticket.ticket_service import TicketService
from upload.upload_service import UploadService
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from storage_node.storage_node_server import StorageNodeServer
from logging_config import get_logger

logger = get_logger(__name__)


def main():
    """Run Storage Node server example."""
    
    # Load configuration
    config = load_config()
    
    # Initialize database
    database = Database(
        host=config.database.host,
        port=config.database.port,
        database=config.database.name,
        user=config.database.user,
        password=config.database.password,
        pool_size=config.database.pool_size
    )
    
    # Initialize Redis
    redis_client = RedisClient(
        host=config.redis.host,
        port=config.redis.port,
        password=config.redis.password,
        pool_size=config.redis.pool_size
    )
    
    # Initialize services
    ticket_service = TicketService(
        redis_client=redis_client,
        upload_ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds,
        download_ticket_ttl_seconds=config.server.download_ticket_ttl_seconds
    )
    
    authorization_service = AuthorizationService(database=database)
    audit_service = AuditService(database=database)
    
    upload_service = UploadService(
        database=database,
        redis_client=redis_client,
        authorization_service=authorization_service,
        audit_service=audit_service,
        notification_service=None,  # Optional: add notification service
        chunk_size=config.server.upload_chunk_size,
        ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds
    )
    
    # Initialize Storage Node server
    storage_node_server = StorageNodeServer(
        host='0.0.0.0',
        port=config.server.storage_port,
        shared_secret=config.server.storage_node_secret,
        ticket_service=ticket_service,
        upload_service=upload_service,
        timeout_seconds=config.server.storage_node_timeout
    )
    
    # Start server
    logger.info("Starting Storage Node server...")
    storage_node_server.start()
    
    logger.info(
        f"Storage Node server listening on port {config.server.storage_port}"
    )
    logger.info(f"Heartbeat timeout: {config.server.storage_node_timeout}s")
    logger.info("Press Ctrl+C to stop")
    
    try:
        # Keep running
        while True:
            time.sleep(1)
            
            # Optionally log connected nodes every 60 seconds
            if int(time.time()) % 60 == 0:
                nodes = storage_node_server.get_connected_nodes()
                logger.info(f"Connected Storage Nodes: {len(nodes)}")
                for node in nodes:
                    logger.info(
                        f"  - {node['node_id']}: "
                        f"healthy={node['healthy']}, "
                        f"connected_at={node['connected_at']}"
                    )
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    finally:
        # Stop server
        storage_node_server.stop()
        logger.info("Storage Node server stopped")


if __name__ == '__main__':
    main()
