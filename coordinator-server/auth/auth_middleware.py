"""Authentication middleware for validating tokens on requests."""
from typing import Optional, Dict, Any, Callable
from auth.auth_service import AuthService
from protocol.message import Message
from protocol.message_types import MessageType
from logging_config import get_logger

logger = get_logger(__name__)


class AuthMiddleware:
    """Middleware for token validation on authenticated requests."""
    
    def __init__(self, auth_service: AuthService):
        """
        Initialize authentication middleware.
        
        Args:
            auth_service: Authentication service instance
        """
        self.auth_service = auth_service
    
    def validate_request(self, message: Message) -> tuple[bool, Optional[Dict[str, Any]], Optional[Message]]:
        """
        Validate authentication token from message payload.
        
        Args:
            message: Incoming message
        
        Returns:
            Tuple of (valid, context, error_message)
            - valid: True if authentication succeeded
            - context: Dict with userId and globalRole if valid
            - error_message: Error message to send if invalid
        """
        # Extract token from payload
        token = message.payload.get('token')
        
        if not token:
            logger.debug("Authentication required: no token provided")
            error_msg = Message.create_error(
                error_code="AUTH_REQUIRED",
                error_message="Authentication token is required",
                request_id=message.request_id
            )
            return False, None, error_msg
        
        # Validate token
        valid, session_data, error_code = self.auth_service.validate_token(token)
        
        if not valid:
            logger.debug(f"Token validation failed: {error_code}")
            error_msg = Message.create_error(
                error_code=error_code or "INVALID_TOKEN",
                error_message="Access token is invalid or has expired",
                details={"token": token[:8] + "..."},
                request_id=message.request_id
            )
            return False, None, error_msg
        
        # Return context with user information
        return True, session_data, None
    
    def require_auth(self, handler: Callable) -> Callable:
        """
        Decorator to require authentication for a handler function.
        
        Args:
            handler: Handler function that takes (message, context)
        
        Returns:
            Wrapped handler that validates authentication first
        """
        def wrapped_handler(message: Message) -> Message:
            # Validate authentication
            valid, context, error_msg = self.validate_request(message)
            
            if not valid:
                return error_msg
            
            # Call original handler with context
            return handler(message, context)
        
        return wrapped_handler
