"""Message handlers for authentication operations."""
from auth.auth_service import AuthService
from protocol.message import Message
from protocol.message_types import MessageType
from logging_config import get_logger

logger = get_logger(__name__)


class AuthHandlers:
    """Handlers for authentication-related messages."""
    
    def __init__(self, auth_service: AuthService):
        """
        Initialize authentication handlers.
        
        Args:
            auth_service: Authentication service instance
        """
        self.auth_service = auth_service
    
    def handle_signup(self, message: Message) -> Message:
        """
        Handle SIGNUP request.
        
        Expected payload:
        {
            "username": "string",
            "email": "string",
            "password": "string"
        }
        
        Response payload (success):
        {
            "userId": "uuid",
            "username": "string",
            "email": "string"
        }
        
        Args:
            message: SIGNUP message
        
        Returns:
            SIGNUP_RESPONSE or ERROR message
        """
        payload = message.payload
        username = payload.get('username')
        email = payload.get('email')
        password = payload.get('password')
        
        # Validate required fields
        if not username or not email or not password:
            return Message.create_error(
                error_code="INVALID_INPUT",
                error_message="Username, email, and password are required",
                request_id=message.request_id
            )
        
        # Attempt signup
        success, user_id, error_code = self.auth_service.signup(username, email, password)
        
        if not success:
            return Message.create_error(
                error_code=error_code,
                error_message=self._get_error_message(error_code),
                request_id=message.request_id
            )
        
        # Return success response
        return Message.create_response(
            message_type=MessageType.SIGNUP_RESPONSE,
            payload={
                "userId": user_id,
                "username": username,
                "email": email
            },
            request_id=message.request_id
        )
    
    def handle_login(self, message: Message) -> Message:
        """
        Handle LOGIN request.
        
        Expected payload:
        {
            "username": "string",
            "password": "string"
        }
        
        Response payload (success):
        {
            "token": "uuid",
            "expiresAt": 1234567890,
            "user": {
                "id": "uuid",
                "username": "string",
                "email": "string",
                "globalRole": "ADMIN"
            }
        }
        
        Args:
            message: LOGIN message
        
        Returns:
            LOGIN_RESPONSE or ERROR message
        """
        payload = message.payload
        username = payload.get('username')
        password = payload.get('password')
        
        # Validate required fields
        if not username or not password:
            return Message.create_error(
                error_code="INVALID_INPUT",
                error_message="Username and password are required",
                request_id=message.request_id
            )
        
        # Attempt login
        success, token, expires_at, user_profile, error_code = self.auth_service.login_with_profile(
            username,
            password,
        )
        
        if not success:
            return Message.create_error(
                error_code=error_code,
                error_message=self._get_error_message(error_code),
                request_id=message.request_id
            )
        
        # Return success response
        logger.info(
            "LOGIN success response keys=%s user_exists=%s user_keys=%s",
            ["token", "expiresAt", "user"],
            bool(user_profile),
            sorted(user_profile.keys()) if isinstance(user_profile, dict) else [],
        )
        return Message.create_response(
            message_type=MessageType.LOGIN_RESPONSE,
            payload={
                "token": token,
                "expiresAt": expires_at,
                "user": user_profile,
            },
            request_id=message.request_id
        )
    
    def handle_logout(self, message: Message) -> Message:
        """
        Handle LOGOUT request.
        
        Expected payload:
        {
            "token": "uuid"
        }
        
        Response payload (success):
        {
            "success": true
        }
        
        Args:
            message: LOGOUT message
        
        Returns:
            LOGOUT_RESPONSE or ERROR message
        """
        payload = message.payload
        token = payload.get('token')
        
        # Validate required fields
        if not token:
            return Message.create_error(
                error_code="INVALID_INPUT",
                error_message="Token is required",
                request_id=message.request_id
            )
        
        # Attempt logout
        success, error_code = self.auth_service.logout(token)
        
        if not success:
            return Message.create_error(
                error_code=error_code,
                error_message=self._get_error_message(error_code),
                request_id=message.request_id
            )
        
        # Return success response
        return Message.create_response(
            message_type=MessageType.LOGOUT_RESPONSE,
            payload={"success": True},
            request_id=message.request_id
        )
    
    def _get_error_message(self, error_code: str) -> str:
        """
        Get human-readable error message for error code.
        
        Args:
            error_code: Error code
        
        Returns:
            Human-readable error message
        """
        error_messages = {
            "DUPLICATE_USERNAME": "Username already exists",
            "DUPLICATE_EMAIL": "Email address already exists",
            "INVALID_CREDENTIALS": "Invalid username or password",
            "INVALID_TOKEN": "Access token is invalid or has expired",
            "AUTH_REQUIRED": "Authentication token is required",
            "INVALID_INPUT": "Invalid input parameters",
            "DATABASE_ERROR": "Database operation failed",
            "REDIS_ERROR": "Session storage operation failed",
            "INTERNAL_ERROR": "Internal server error"
        }
        
        return error_messages.get(error_code, "Unknown error")
