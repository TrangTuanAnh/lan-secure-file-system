"""Test script to verify project setup."""
import sys
import pytest
from config import load_config
from database import Database
from redis_client import RedisClient
from logging_config import setup_logging, get_logger

setup_logging(level='INFO')
logger = get_logger(__name__)


@pytest.fixture
def config():
    """Load configuration once for setup tests."""
    return load_test_config()


def load_test_config():
    """Test configuration loading."""
    print("\n=== Testing Configuration ===")
    try:
        config = load_config()
        print(f"[OK] Configuration loaded successfully")
        print(f"  Database: {config.database.host}:{config.database.port}/{config.database.name}")
        print(f"  Redis: {config.redis.host}:{config.redis.port}")
        print(f"  Server Ports: Client={config.server.client_port}, "
              f"Storage={config.server.storage_port}, "
              f"Notification={config.server.notification_port}")
        return config
    except Exception as e:
        print(f"[FAIL] Configuration loading failed: {e}")
        return None


def test_config(config):
    """Test configuration loading."""
    assert config is not None


def check_database(config):
    """Test database connection."""
    print("\n=== Testing Database Connection ===")
    try:
        db = Database(config.database)
        db.connect()
        print(f"[OK] Database connection pool created")
        
        # Test query
        result = db.execute_query("SELECT 1 as test, NOW() as current_time")
        print(f"[OK] Test query successful: {result}")
        
        db.close()
        print(f"[OK] Database connection closed")
        return True
    except Exception as e:
        print(f"[FAIL] Database test failed: {e}")
        return False


def test_database(config):
    """Test database connection."""
    assert check_database(config) is True


def check_redis(config):
    """Test Redis connection."""
    print("\n=== Testing Redis Connection ===")
    try:
        redis_client = RedisClient(config.redis)
        redis_client.connect()
        print(f"[OK] Redis connection established")
        
        # Test ping
        if redis_client.ping():
            print(f"[OK] Redis ping successful")
        else:
            print(f"[FAIL] Redis ping failed")
            return False
        
        # Test session storage
        test_token = "test-token-123"
        test_data = {"userId": "test-user", "globalRole": "USER"}
        redis_client.set_session(test_token, test_data, 60)
        print(f"[OK] Session stored in Redis")
        
        retrieved = redis_client.get_session(test_token)
        if retrieved == test_data:
            print(f"[OK] Session retrieved successfully: {retrieved}")
        else:
            print(f"[FAIL] Session retrieval mismatch: expected {test_data}, got {retrieved}")
            return False
        
        redis_client.delete_session(test_token)
        print(f"[OK] Session deleted")
        
        redis_client.close()
        print(f"[OK] Redis connection closed")
        return True
    except Exception as e:
        print(f"[FAIL] Redis test failed: {e}")
        return False


def test_redis(config):
    """Test Redis connection."""
    assert check_redis(config) is True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Coordinator Server Setup Test")
    print("=" * 60)
    
    # Test configuration
    config = load_test_config()
    if not config:
        print("\n[FAIL] Setup test failed: Configuration error")
        sys.exit(1)
    
    # Test database
    db_ok = check_database(config)
    
    # Test Redis
    redis_ok = check_redis(config)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Configuration: [OK]")
    print(f"Database: {'[OK]' if db_ok else '[FAIL]'}")
    print(f"Redis: {'[OK]' if redis_ok else '[FAIL]'}")
    
    if db_ok and redis_ok:
        print("\n[OK] All tests passed! Setup is complete.")
        sys.exit(0)
    else:
        print("\n[FAIL] Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
