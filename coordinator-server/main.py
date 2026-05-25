"""Main entry point for Coordinator Server."""
import sys
import signal
import threading
from config import load_config
from database import Database
from redis_client import RedisClient
from cleanup.cleanup_service import CleanupService
from auth.auth_service import AuthService
from auth.authorization_service import AuthorizationService
from room.room_service import RoomService
from file.file_service import FileService
from upload.upload_service import UploadService
from download.download_service import DownloadService
from notification.notification_service import NotificationService
from health.health_service import HealthService
from audit.audit_service import AuditService
from ticket.ticket_service import TicketService
from client_socket_server import ClientSocketServer
from storage_node.storage_node_server import StorageNodeServer
from storage_node.registry import StorageNodeRegistry
from storage_node.reconciliation_service import ReconciliationService
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)

# Global references for cleanup
cleanup_service = None
client_server = None
storage_node_server = None
shutdown_event = threading.Event()


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully.

    Works cross-platform (Windows/Linux/macOS). Sets an event that the
    main thread waits on via Event.wait() instead of signal.pause()
    (which is Unix-only).
    """
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


def main():
    """Initialize and start the Coordinator Server."""
    global cleanup_service, client_server, storage_node_server
    
    # Setup logging
    setup_logging(level='INFO')
    logger.info("Starting Coordinator Server...")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize database
    db = Database(config.database)
    try:
        db.connect()
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    # Initialize Redis
    redis_client = RedisClient(config.redis)
    try:
        redis_client.connect()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        db.close()
        sys.exit(1)
    
    # Test connections
    try:
        # Test database
        result = db.execute_query("SELECT 1 as test")
        logger.info(f"Database test query successful: {result}")
        
        # Test Redis
        if redis_client.ping():
            logger.info("Redis ping successful")
        else:
            logger.warning("Redis ping failed")
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        redis_client.close()
        db.close()
        sys.exit(1)
    
    # Initialize services
    try:
        logger.info("Initializing services...")
        
        # Core services
        audit_service = AuditService(db)
        auth_service = AuthService(db, redis_client, config.server.session_ttl_seconds, audit_service)
        authorization_service = AuthorizationService(db)
        ticket_service = TicketService(
            redis_client,
            config.server.upload_ticket_ttl_seconds,
            config.server.download_ticket_ttl_seconds
        )
        storage_registry = StorageNodeRegistry(
            timeout_seconds=config.server.storage_node_timeout
        )
        reconciliation_service = ReconciliationService(db)
        
        # Business logic services
        notification_service = NotificationService()
        room_service = RoomService(db, audit_service, notification_service)
        file_service = FileService(db, audit_service, notification_service)
        upload_service = UploadService(
            database=db,
            redis_client=redis_client,
            authorization_service=authorization_service,
            audit_service=audit_service,
            notification_service=notification_service,
            chunk_size=config.server.upload_chunk_size,
            ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds,
            storage_registry=storage_registry,
            ticket_secret=config.server.storage_node_secret
        )
        download_service = DownloadService(
            database=db,
            redis_client=redis_client,
            authorization_service=authorization_service,
            audit_service=audit_service,
            ticket_ttl_seconds=config.server.download_ticket_ttl_seconds,
            storage_registry=storage_registry,
            ticket_secret=config.server.storage_node_secret
        )
        health_service = HealthService(db, redis_client, storage_registry)
        
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        redis_client.close()
        db.close()
        sys.exit(1)
    
    # Initialize and start cleanup service
    try:
        cleanup_service = CleanupService(
            db,
            interval_seconds=600,
            storage_registry=storage_registry
        )  # 10 minutes
        cleanup_service.start()
        logger.info("Cleanup service started")
    except Exception as e:
        logger.error(f"Failed to start cleanup service: {e}")
        redis_client.close()
        db.close()
        sys.exit(1)
    
    # Initialize and start client socket server
    try:
        client_server = ClientSocketServer(
            host='0.0.0.0',
            port=config.server.client_port,
            auth_service=auth_service,
            authorization_service=authorization_service,
            room_service=room_service,
            file_service=file_service,
            upload_service=upload_service,
            download_service=download_service,
            notification_service=notification_service,
            health_service=health_service
        )
        client_server.start()
        logger.info(f"Client socket server started on port {config.server.client_port}")
    except Exception as e:
        logger.error(f"Failed to start client socket server: {e}", exc_info=True)
        if cleanup_service:
            cleanup_service.stop()
        redis_client.close()
        db.close()
        sys.exit(1)
    
    # Initialize and start storage node server
    try:
        storage_node_server = StorageNodeServer(
            host='0.0.0.0',
            port=config.server.storage_port,
            shared_secret=config.server.storage_node_secret,
            ticket_service=ticket_service,
            upload_service=upload_service,
            timeout_seconds=config.server.storage_node_timeout,
            registry=storage_registry,
            reconciliation_service=reconciliation_service,
            audit_service=audit_service,
        )
        storage_node_server.start()
        logger.info(f"Storage node server started on port {config.server.storage_port}")
    except Exception as e:
        logger.error(f"Failed to start storage node server: {e}", exc_info=True)
        if client_server:
            client_server.stop()
        if cleanup_service:
            cleanup_service.stop()
        redis_client.close()
        db.close()
        sys.exit(1)
    
    logger.info("Coordinator Server initialized successfully")
    logger.info(f"Configuration: Client Port={config.server.client_port}, "
                f"Storage Port={config.server.storage_port}, "
                f"Notification Port={config.server.notification_port}")
    logger.info("Server is ready to accept connections")
    
    # Keep main thread alive (cross-platform: works on Windows too)
    try:
        # Block until shutdown_handler fires or KeyboardInterrupt
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    # Cleanup
    try:
        if client_server:
            logger.info("Stopping client socket server...")
            client_server.stop()
        if storage_node_server:
            logger.info("Stopping storage node server...")
            storage_node_server.stop()
        if cleanup_service:
            logger.info("Stopping cleanup service...")
            cleanup_service.stop()
        redis_client.close()
        db.close()
        logger.info("Coordinator Server shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
