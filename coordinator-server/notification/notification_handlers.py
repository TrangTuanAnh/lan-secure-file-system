"""Notification handlers for SUBSCRIBE_ROOM and UNSUBSCRIBE_ROOM."""
from protocol.socket_server import SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType
from auth.auth_service import AuthService
from auth.authorization_service import AuthorizationService
from notification.notification_service import NotificationService
from logging_config import get_logger

logger = get_logger(__name__)


class NotificationHandlers:
    """Handlers for notification-related messages."""
    
    def __init__(
        self,
        notification_service: NotificationService,
        authorization_service: AuthorizationService,
        auth_service: AuthService
    ):
        """
        Initialize notification handlers.
        
        Args:
            notification_service: Notification service instance
            authorization_service: Authorization service instance
            auth_service: Authentication service instance
        """
        self.notification = notification_service
        self.authz = authorization_service
        self.auth = auth_service
    
    def handle_subscribe_room(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle SUBSCRIBE_ROOM request.
        
        Requirements: 9.1, 9.2, 9.3
        
        Process:
        1. Require access token authentication
        2. Verify user is member of room or ADMIN
        3. Add connection to subscriber map for room
        4. Return success response
        
        Args:
            connection: Socket connection
            message: SUBSCRIBE_ROOM message
        """
        try:
            # Extract token from payload
            token = message.payload.get("token")
            
            if not token:
                response = Message.create_error(
                    "AUTH_REQUIRED",
                    "Authentication token is required",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return
            
            # Validate token
            valid, session_data, error_code = self.auth.validate_token(token)
            
            if not valid:
                response = Message.create_error(
                    error_code or "INVALID_TOKEN",
                    "Access token is invalid or has expired",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return
            
            user_id = session_data['userId']
            global_role = session_data['globalRole']
            
            # Extract room_id from payload
            room_id = message.payload.get("roomId")
            
            if not room_id:
                response = Message.create_error(
                    "INVALID_REQUEST",
                    "roomId is required",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return
            
            # Check permission (user must be member of room or ADMIN)
            has_permission = self.authz.check_permission(
                user_id=user_id,
                room_id=room_id,
                action="VIEW_FILES",  # Any room member can subscribe
                global_role=global_role
            )
            
            if not has_permission:
                response = Message.create_error(
                    "PERMISSION_DENIED",
                    "User is not a member of this room",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return
            
            # Add connection to subscriber map
            self.notification.add_subscriber(room_id, connection)
            
            # Send success response
            response = Message(
                type=MessageType.SUBSCRIBE_ROOM_RESPONSE,
                request_id=message.request_id,
                payload={
                    "success": True,
                    "roomId": room_id
                }
            )
            connection.send_message(response)
            
            logger.info(f"User {user_id} subscribed to room {room_id}")
        
        except Exception as e:
            logger.error(f"Error handling SUBSCRIBE_ROOM: {e}", exc_info=True)
            response = Message.create_error(
                "INTERNAL_ERROR",
                "Failed to subscribe to room",
                request_id=message.request_id
            )
            connection.send_message(response)
    
    def handle_unsubscribe_room(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle UNSUBSCRIBE_ROOM request.
        
        Requirements: 9.4
        
        Process:
        1. Remove connection from subscriber map for room
        2. Return success response
        
        Args:
            connection: Socket connection
            message: UNSUBSCRIBE_ROOM message
        """
        try:
            # Require auth token (consistent with SUBSCRIBE_ROOM)
            token = message.payload.get("token")
            if not token:
                response = Message.create_error(
                    "AUTH_REQUIRED",
                    "Authentication token is required",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return

            valid, session_data, error_code = self.auth.validate_token(token)
            if not valid:
                response = Message.create_error(
                    error_code or "INVALID_TOKEN",
                    "Access token is invalid or has expired",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return

            user_id = session_data.get('userId')

            # Extract room_id from payload
            room_id = message.payload.get("roomId")

            if not room_id:
                response = Message.create_error(
                    "INVALID_REQUEST",
                    "roomId is required",
                    request_id=message.request_id
                )
                connection.send_message(response)
                return

            # Remove connection from subscriber map
            self.notification.remove_subscriber(room_id, connection)

            # Send success response
            response = Message(
                type=MessageType.UNSUBSCRIBE_ROOM_RESPONSE,
                request_id=message.request_id,
                payload={
                    "success": True,
                    "roomId": room_id
                }
            )
            connection.send_message(response)

            logger.info(f"User {user_id} (conn {connection.connection_id}) unsubscribed from room {room_id}")
        
        except Exception as e:
            logger.error(f"Error handling UNSUBSCRIBE_ROOM: {e}", exc_info=True)
            response = Message.create_error(
                "INTERNAL_ERROR",
                "Failed to unsubscribe from room",
                request_id=message.request_id
            )
            connection.send_message(response)
