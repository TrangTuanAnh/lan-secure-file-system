"""Test script to verify project setup."""
import sys
from config import load_config
from database import Database
from redis_client import RedisClient
from logging_config import setup_logging, get_logger

setup_logging(level='INFO')
logger = get_logger(__name__)


def test_config():
    """Test configuration loading."""
    print("\n=== Testing Configuration ===")
    try:
        config = load_config()
        print(f"✓ Configuration loaded successfully")
        print(f"  Database: {config.database.host}:{config.database.port}/{config.database.name}")
        print(f"  Redis: {config.redis.host}:{config.redis.port}")
        print(f"  Server Ports: Client={config.server.client_port}, "
              f"Storage={config.server.storage_port}, "
              f"Notification={config.server.notification_port}")
        return config
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return None


def test_database(config):
    """Test database connection."""
    print("\n=== Testing Database Connection ===")
    try:
        db = Database(config.database)
        db.connect()
        print(f"✓ Database connection pool created")
        
        # Test query
        result = db.execute_query("SELECT 1 as test, NOW() as current_time")
        print(f"✓ Test query successful: {result}")
        
        db.close()
        print(f"✓ Database connection closed")
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def test_redis(config):
    """Test Redis connection."""
    print("\n=== Testing Redis Connection ===")
    try:
        redis_client = RedisClient(config.redis)
        redis_client.connect()
        print(f"✓ Redis connection established")
        
        # Test ping
        if redis_client.ping():
            print(f"✓ Redis ping successful")
        else:
            print(f"✗ Redis ping failed")
            return False
        
        # Test session storage
        test_token = "test-token-123"
        test_data = {"userId": "test-user", "globalRole": "USER"}
        redis_client.set_session(test_token, test_data, 60)
        print(f"✓ Session stored in Redis")
        
        retrieved = redis_client.get_session(test_token)
        if retrieved == test_data:
            print(f"✓ Session retrieved successfully: {retrieved}")
        else:
            print(f"✗ Session retrieval mismatch: expected {test_data}, got {retrieved}")
            return False
        
        redis_client.delete_session(test_token)
        print(f"✓ Session deleted")
        
        redis_client.close()
        print(f"✓ Redis connection closed")
        return True
    except Exception as e:
        print(f"✗ Redis test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Coordinator Server Setup Test")
    print("=" * 60)
    
    # Test configuration
    config = test_config()
    if not config:
        print("\n✗ Setup test failed: Configuration error")
        sys.exit(1)
    
    # Test database
    db_ok = test_database(config)
    
    # Test Redis
    redis_ok = test_redis(config)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Configuration: ✓")
    print(f"Database: {'✓' if db_ok else '✗'}")
    print(f"Redis: {'✓' if redis_ok else '✗'}")
    
    if db_ok and redis_ok:
        print("\n✓ All tests passed! Setup is complete.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
