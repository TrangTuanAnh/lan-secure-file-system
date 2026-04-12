"""Main entry point for Coordinator Server."""
import sys
import signal
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
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)

# Global references for cleanup
cleanup_service = None
client_server = None


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global cleanup_service, client_server
    logger.info(f"Received signal {signum}, shutting down...")
    
    if client_server:
        logger.info("Stopping client socket server...")
        client_server.stop()
    
    if cleanup_service:
        logger.info("Stopping cleanup service...")
        cleanup_service.stop()
    
    sys.exit(0)


def main():
    """Initialize and start the Coordinator Server."""
    global cleanup_service, client_server
    
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
        
        # Business logic services
        notification_service = NotificationService()
        room_service = RoomService(db, authorization_service, audit_service, notification_service)
        file_service = FileService(db, authorization_service)
        upload_service = UploadService(
            db,
            authorization_service,
            ticket_service,
            audit_service,
            notification_service,
            config.server.upload_chunk_size
        )
        download_service = DownloadService(
            db,
            authorization_service,
            ticket_service,
            audit_service
        )
        health_service = HealthService(db, redis_client)
        
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        redis_client.close()
        db.close()
        sys.exit(1)
    
    # Initialize and start cleanup service
    try:
        cleanup_service = CleanupService(db, interval_seconds=600)  # 10 minutes
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
    
    logger.info("Coordinator Server initialized successfully")
    logger.info(f"Configuration: Client Port={config.server.client_port}, "
                f"Storage Port={config.server.storage_port}, "
                f"Notification Port={config.server.notification_port}")
    logger.info("Server is ready to accept connections")
    
    # Keep main thread alive
    try:
        signal.pause()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    # Cleanup
    try:
        if client_server:
            logger.info("Stopping client socket server...")
            client_server.stop()
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
