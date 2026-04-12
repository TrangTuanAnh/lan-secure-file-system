"""Message handlers for health check operations."""
from health.health_service import HealthService
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.socket_server import SocketConnection
from logging_config import get_logger

logger = get_logger(__name__)


class HealthHandlers:
    """
    Handlers for health check messages.
    
    Requirements: 13.1, 13.2, 13.3
    """
    
    def __init__(self, health_service: HealthService):
        """
        Initialize health check handlers.
        
        Args:
            health_service: Health service instance
        """
        self.health_service = health_service
    
    def handle_ping(self, connection: SocketConnection, message: Message) -> None:
        """
        Handle PING request (no authentication required).
        
        Requirements: 13.1, 13.2
        
        Args:
            connection: Connection that sent the message
            message: PING message
        """
        logger.debug(f"PING received from {connection.connection_id}")
        
        # Get ping response
        ping_data = self.health_service.ping()
        
        # Send PONG response
        response = Message.create_response(
            MessageType.PONG,
            ping_data,
            request_id=message.request_id
        )
        connection.send_message(response)
    
    def handle_status(self, connection: SocketConnection, message: Message) -> None:
        """
        Handle STATUS request (no authentication required).
        
        Requirements: 13.3
        
        Args:
            connection: Connection that sent the message
            message: STATUS message
        """
        logger.debug(f"STATUS received from {connection.connection_id}")
        
        try:
            # Get system status
            status_data = self.health_service.get_status()
            
            # Send STATUS_RESPONSE
            response = Message.create_response(
                MessageType.STATUS_RESPONSE,
                status_data,
                request_id=message.request_id
            )
            connection.send_message(response)
        
        except Exception as e:
            logger.error(f"Error handling STATUS request: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "Failed to retrieve system status",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
