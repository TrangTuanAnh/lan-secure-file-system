"""Example integration of health check handlers with socket server."""
from config import load_config
from database import Database
from redis_client import RedisClient
from protocol.socket_server import BaseSocketServer
from protocol.message_types import MessageType
from health.health_service import HealthService
from health.health_handlers import HealthHandlers
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)


def main():
    """Example of integrating health check handlers."""
    # Setup logging
    setup_logging(level='INFO')
    
    # Load configuration
    config = load_config()
    
    # Initialize database
    db = Database(config.database)
    db.connect()
    
    # Initialize Redis
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    # Initialize health service (without storage node server for this example)
    health_service = HealthService(db, redis_client, storage_node_server=None)
    
    # Initialize health handlers
    health_handlers = HealthHandlers(health_service)
    
    # Create socket server
    server = BaseSocketServer(
        host=config.server.client_host,
        port=config.server.client_port,
        name="ClientServer"
    )
    
    # Register health check handlers
    # IMPORTANT: These handlers do NOT require authentication
    server.register_handler(MessageType.PING, health_handlers.handle_ping)
    server.register_handler(MessageType.STATUS, health_handlers.handle_status)
    
    logger.info("Health check handlers registered")
    logger.info("PING and STATUS endpoints are available without authentication")
    
    # Start server
    server.start()
    logger.info(f"Server started on {config.server.client_host}:{config.server.client_port}")
    
    # Keep running
    try:
        import signal
        signal.pause()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    # Cleanup
    server.stop()
    redis_client.close()
    db.close()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
