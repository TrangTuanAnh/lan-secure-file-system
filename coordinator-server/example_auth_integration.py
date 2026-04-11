"""Example demonstrating authentication module integration."""
from config import load_config
from database import Database
from redis_client import RedisClient
from auth.auth_service import AuthService
from auth.auth_handlers import AuthHandlers
from auth.auth_middleware import AuthMiddleware
from protocol.message import Message
from protocol.message_types import MessageType
from logging_config import setup_logging, get_logger

setup_logging(level='INFO')
logger = get_logger(__name__)


def example_authentication_flow():
    """Demonstrate complete authentication flow."""
    
    # Load configuration
    config = load_config()
    
    # Initialize database and Redis
    db = Database(config.database)
    db.connect()
    
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    # Initialize authentication service and handlers
    auth_service = AuthService(db, redis_client, config.server.session_ttl_seconds)
    auth_handlers = AuthHandlers(auth_service)
    auth_middleware = AuthMiddleware(auth_service)
    
    logger.info("=== Authentication Module Integration Example ===\n")
    
    # 1. User Signup
    logger.info("1. Testing user signup...")
    signup_msg = Message.create_request(
        message_type=MessageType.SIGNUP,
        payload={
            "username": "demo_user",
            "email": "demo@example.com",
            "password": "secure_password_123"
        }
    )
    
    signup_response = auth_handlers.handle_signup(signup_msg)
    if signup_response.type == MessageType.SIGNUP_RESPONSE:
        logger.info(f"✓ Signup successful: {signup_response.payload}")
    else:
        logger.error(f"✗ Signup failed: {signup_response.payload}")
        return
    
    # 2. User Login
    logger.info("\n2. Testing user login...")
    login_msg = Message.create_request(
        message_type=MessageType.LOGIN,
        payload={
            "username": "demo_user",
            "password": "secure_password_123"
        }
    )
    
    login_response = auth_handlers.handle_login(login_msg)
    if login_response.type == MessageType.LOGIN_RESPONSE:
        token = login_response.payload['token']
        expires_at = login_response.payload['expiresAt']
        logger.info(f"✓ Login successful")
        logger.info(f"  Token: {token}")
        logger.info(f"  Expires at: {expires_at}")
    else:
        logger.error(f"✗ Login failed: {login_response.payload}")
        return
    
    # 3. Token Validation (Middleware)
    logger.info("\n3. Testing token validation...")
    authenticated_request = Message.create_request(
        message_type=MessageType.LIST_ROOMS,
        payload={"token": token}
    )
    
    valid, context, error_msg = auth_middleware.validate_request(authenticated_request)
    if valid:
        logger.info(f"✓ Token validation successful")
        logger.info(f"  User ID: {context['userId']}")
        logger.info(f"  Global Role: {context['globalRole']}")
    else:
        logger.error(f"✗ Token validation failed: {error_msg.payload}")
        return
    
    # 4. Invalid Token Test
    logger.info("\n4. Testing invalid token...")
    invalid_request = Message.create_request(
        message_type=MessageType.LIST_ROOMS,
        payload={"token": "invalid_token_12345"}
    )
    
    valid, context, error_msg = auth_middleware.validate_request(invalid_request)
    if not valid:
        logger.info(f"✓ Invalid token correctly rejected")
        logger.info(f"  Error: {error_msg.get_error_code()} - {error_msg.get_error_message()}")
    else:
        logger.error(f"✗ Invalid token was accepted (should have been rejected)")
    
    # 5. User Logout
    logger.info("\n5. Testing user logout...")
    logout_msg = Message.create_request(
        message_type=MessageType.LOGOUT,
        payload={"token": token}
    )
    
    logout_response = auth_handlers.handle_logout(logout_msg)
    if logout_response.type == MessageType.LOGOUT_RESPONSE:
        logger.info(f"✓ Logout successful: {logout_response.payload}")
    else:
        logger.error(f"✗ Logout failed: {logout_response.payload}")
    
    # 6. Verify Token is Invalid After Logout
    logger.info("\n6. Testing token after logout...")
    valid, context, error_msg = auth_middleware.validate_request(authenticated_request)
    if not valid:
        logger.info(f"✓ Token correctly invalidated after logout")
        logger.info(f"  Error: {error_msg.get_error_code()}")
    else:
        logger.error(f"✗ Token still valid after logout (should be invalid)")
    
    # 7. Test Duplicate Username
    logger.info("\n7. Testing duplicate username...")
    duplicate_signup = Message.create_request(
        message_type=MessageType.SIGNUP,
        payload={
            "username": "demo_user",
            "email": "another@example.com",
            "password": "password123"
        }
    )
    
    duplicate_response = auth_handlers.handle_signup(duplicate_signup)
    if duplicate_response.type == MessageType.ERROR:
        logger.info(f"✓ Duplicate username correctly rejected")
        logger.info(f"  Error: {duplicate_response.get_error_code()}")
    else:
        logger.error(f"✗ Duplicate username was accepted (should have been rejected)")
    
    # 8. Test Invalid Login
    logger.info("\n8. Testing invalid login credentials...")
    invalid_login = Message.create_request(
        message_type=MessageType.LOGIN,
        payload={
            "username": "demo_user",
            "password": "wrong_password"
        }
    )
    
    invalid_login_response = auth_handlers.handle_login(invalid_login)
    if invalid_login_response.type == MessageType.ERROR:
        logger.info(f"✓ Invalid credentials correctly rejected")
        logger.info(f"  Error: {invalid_login_response.get_error_code()}")
    else:
        logger.error(f"✗ Invalid credentials were accepted (should have been rejected)")
    
    logger.info("\n=== Authentication Module Integration Test Complete ===")
    
    # Cleanup
    redis_client.close()
    db.close()


if __name__ == "__main__":
    example_authentication_flow()
