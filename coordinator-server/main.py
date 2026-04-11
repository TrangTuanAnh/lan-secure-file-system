"""Main entry point for Coordinator Server."""
import sys
from config import load_config
from database import Database
from redis_client import RedisClient
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)


def main():
    """Initialize and start the Coordinator Server."""
    # Setup logging
    setup_logging(level='INFO')
    logger.info("Starting Coordinator Server...")
    
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
    
    logger.info("Coordinator Server initialized successfully")
    logger.info(f"Configuration: Client Port={config.server.client_port}, "
                f"Storage Port={config.server.storage_port}, "
                f"Notification Port={config.server.notification_port}")
    
    # TODO: Start socket servers here
    
    # Cleanup
    try:
        redis_client.close()
        db.close()
        logger.info("Coordinator Server shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
