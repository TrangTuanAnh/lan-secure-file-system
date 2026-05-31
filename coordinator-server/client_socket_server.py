"""Client socket server for handling client connections."""
from typing import Dict, Callable, Optional
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType
from auth.auth_service import AuthService
from auth.auth_middleware import AuthMiddleware
from auth.auth_handlers import AuthHandlers
from auth.authorization_service import AuthorizationService
from room.room_service import RoomService
from room.room_handlers import RoomHandlers
from file.file_service import FileService
from file.file_handlers import FileHandlers
from upload.upload_service import UploadService
from upload.upload_handlers import UploadHandlers
from download.download_service import DownloadService
from download.download_handlers import DownloadHandlers
from notification.notification_service import NotificationService
from notification.notification_handlers import NotificationHandlers
from health.health_service import HealthService
from health.health_handlers import HealthHandlers
from logging_config import get_logger

logger = get_logger(__name__)


class ClientSocketServer(BaseSocketServer):
    """
    Socket server for client connections.
    
    Handles:
    - Authentication (SIGNUP, LOGIN, LOGOUT)
    - Room management (CREATE_ROOM, ADD_MEMBER, etc.)
    - File operations (LIST_FILES, FILE_DETAIL, etc.)
    - Upload initialization (INIT_UPLOAD)
    - Download initialization (INIT_DOWNLOAD)
    - Share tokens (CREATE_SHARE_TOKEN)
    - Notifications (SUBSCRIBE_ROOM, UNSUBSCRIBE_ROOM)
    - Health checks (PING, STATUS)
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        auth_service: AuthService,
        authorization_service: AuthorizationService,
        room_service: RoomService,
        file_service: FileService,
        upload_service: UploadService,
        download_service: DownloadService,
        notification_service: NotificationService,
        health_service: HealthService,
        max_workers: int = 8,
        ssl_context=None,
    ):
        """
        Initialize client socket server.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            auth_service: Authentication service
            authorization_service: Authorization service
            room_service: Room management service
            file_service: File metadata service
            upload_service: Upload control service
            download_service: Download control service
            notification_service: Notification service
            health_service: Health check service
        """
        super().__init__(
            host, port, name="ClientSocketServer",
            max_workers=max_workers, ssl_context=ssl_context,
        )
        
        # Services
        self.auth_service = auth_service
        self.authorization_service = authorization_service
        self.room_service = room_service
        self.file_service = file_service
        self.upload_service = upload_service
        self.download_service = download_service
        self.notification_service = notification_service
        self.health_service = health_service
        
        # Middleware
        self.auth_middleware = AuthMiddleware(auth_service)
        
        # Handlers
        self.auth_handlers = AuthHandlers(auth_service)
        self.room_handlers = RoomHandlers(room_service)
        self.file_handlers = FileHandlers(file_service)
        self.upload_handlers = UploadHandlers(upload_service)
        self.download_handlers = DownloadHandlers(download_service)
        self.notification_handlers = NotificationHandlers(
            notification_service,
            authorization_service,
            auth_service
        )
        self.health_handlers = HealthHandlers(health_service)
        
        # Register message handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register all message type handlers."""
        # Authentication (no auth required)
        self.register_handler(MessageType.SIGNUP, self._handle_signup)
        self.register_handler(MessageType.LOGIN, self._handle_login)
        self.register_handler(MessageType.LOGOUT, self._handle_logout)
        
        # Room management (auth required)
        self.register_handler(MessageType.CREATE_ROOM, self._handle_create_room)
        self.register_handler(MessageType.ADD_MEMBER, self._handle_add_member)
        self.register_handler(MessageType.REMOVE_MEMBER, self._handle_remove_member)
        self.register_handler(MessageType.SET_ROLE, self._handle_set_role)
        self.register_handler(MessageType.LIST_ROOMS, self._handle_list_rooms)
        self.register_handler(MessageType.LIST_MEMBERS, self._handle_list_members)
        
        # File operations (auth required)
        self.register_handler(MessageType.LIST_FILES, self._handle_list_files)
        self.register_handler(MessageType.FILE_DETAIL, self._handle_file_detail)
        self.register_handler(MessageType.FILE_VERSIONS, self._handle_file_versions)
        self.register_handler(MessageType.DELETE_FILE, self._handle_delete_file)
        
        # Upload (auth required)
        self.register_handler(MessageType.INIT_UPLOAD, self._handle_init_upload)
        
        # Download (auth required or share token)
        self.register_handler(MessageType.INIT_DOWNLOAD, self._handle_init_download)
        
        # Share tokens (auth required)
        self.register_handler(MessageType.CREATE_SHARE_TOKEN, self._handle_create_share_token)
        
        # Notifications (auth required)
        self.register_handler(MessageType.SUBSCRIBE_ROOM, self._handle_subscribe_room)
        self.register_handler(MessageType.UNSUBSCRIBE_ROOM, self._handle_unsubscribe_room)
        
        # Health checks (no auth required)
        self.register_handler(MessageType.PING, self._handle_ping)
        self.register_handler(MessageType.STATUS, self._handle_status)
    
    # Authentication handlers (no auth required)
    
    def _handle_signup(self, connection: SocketConnection, message: Message) -> None:
        """Handle SIGNUP request."""
        try:
            response = self.auth_handlers.handle_signup(message)
            connection.send_message(response)
        except Exception as e:
            logger.error(f"Error handling SIGNUP: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_login(self, connection: SocketConnection, message: Message) -> None:
        """Handle LOGIN request."""
        try:
            response = self.auth_handlers.handle_login(message)
            connection.send_message(response)
        except Exception as e:
            logger.error(f"Error handling LOGIN: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_logout(self, connection: SocketConnection, message: Message) -> None:
        """Handle LOGOUT request."""
        try:
            response = self.auth_handlers.handle_logout(message)
            connection.send_message(response)
        except Exception as e:
            logger.error(f"Error handling LOGOUT: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    # Room management handlers (auth required)
    
    def _handle_create_room(self, connection: SocketConnection, message: Message) -> None:
        """Handle CREATE_ROOM request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_create_room(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_add_member(self, connection: SocketConnection, message: Message) -> None:
        """Handle ADD_MEMBER request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_add_member(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_remove_member(self, connection: SocketConnection, message: Message) -> None:
        """Handle REMOVE_MEMBER request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_remove_member(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_set_role(self, connection: SocketConnection, message: Message) -> None:
        """Handle SET_ROLE request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_set_role(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_list_rooms(self, connection: SocketConnection, message: Message) -> None:
        """Handle LIST_ROOMS request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_list_rooms(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_list_members(self, connection: SocketConnection, message: Message) -> None:
        """Handle LIST_MEMBERS request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.room_handlers.handle_list_members(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    # File operation handlers (auth required)
    
    def _handle_list_files(self, connection: SocketConnection, message: Message) -> None:
        """Handle LIST_FILES request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.file_handlers.handle_list_files(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_file_detail(self, connection: SocketConnection, message: Message) -> None:
        """Handle FILE_DETAIL request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.file_handlers.handle_file_detail(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_file_versions(self, connection: SocketConnection, message: Message) -> None:
        """Handle FILE_VERSIONS request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.file_handlers.handle_file_versions(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    def _handle_delete_file(self, connection: SocketConnection, message: Message) -> None:
        """Handle DELETE_FILE request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.file_handlers.handle_delete_file(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    # Upload handler (auth required)
    
    def _handle_init_upload(self, connection: SocketConnection, message: Message) -> None:
        """Handle INIT_UPLOAD request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self.upload_handlers.handle_init_upload(
                msg, ctx['userId'], ctx['globalRole']
            )
        )
    
    # Download handler (auth required or share token)
    
    def _handle_init_download(self, connection: SocketConnection, message: Message) -> None:
        """Handle INIT_DOWNLOAD request (supports both auth token and share token)."""
        try:
            # Check if share token is provided
            share_token = message.payload.get('shareToken')
            
            if share_token:
                # Handle download with share token (no auth required)
                response_dict = self.download_handlers.handle_init_download_share(message.payload)
                
                # Convert dict response to Message
                if response_dict['type'] == 'ERROR':
                    response = Message.create_error(
                        response_dict['error']['code'],
                        response_dict['error']['message'],
                        request_id=message.request_id
                    )
                else:
                    response = Message.create_response(
                        MessageType.DOWNLOAD_PLAN,
                        response_dict['payload'],
                        request_id=message.request_id
                    )
                
                connection.send_message(response)
            else:
                # Handle download with auth token (auth required)
                self._handle_authenticated_request(
                    connection,
                    message,
                    lambda msg, ctx: self._handle_init_download_authenticated(msg, ctx)
                )
        except Exception as e:
            logger.error(f"Error handling INIT_DOWNLOAD: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_init_download_authenticated(self, message: Message, context: Dict) -> Message:
        """Handle authenticated INIT_DOWNLOAD request."""
        response_dict = self.download_handlers.handle_init_download(
            context['userId'],
            context['globalRole'],
            message.payload
        )
        
        # Convert dict response to Message
        if response_dict['type'] == 'ERROR':
            return Message.create_error(
                response_dict['error']['code'],
                response_dict['error']['message'],
                request_id=message.request_id
            )
        else:
            return Message.create_response(
                MessageType.DOWNLOAD_PLAN,
                response_dict['payload'],
                request_id=message.request_id
            )
    
    # Share token handler (auth required)
    
    def _handle_create_share_token(self, connection: SocketConnection, message: Message) -> None:
        """Handle CREATE_SHARE_TOKEN request."""
        self._handle_authenticated_request(
            connection,
            message,
            lambda msg, ctx: self._handle_create_share_token_authenticated(msg, ctx)
        )
    
    def _handle_create_share_token_authenticated(self, message: Message, context: Dict) -> Message:
        """Handle authenticated CREATE_SHARE_TOKEN request."""
        response_dict = self.download_handlers.handle_create_share_token(
            context['userId'],
            context['globalRole'],
            message.payload
        )
        
        # Convert dict response to Message
        if response_dict['type'] == 'ERROR':
            return Message.create_error(
                response_dict['error']['code'],
                response_dict['error']['message'],
                request_id=message.request_id
            )
        else:
            return Message.create_response(
                MessageType.CREATE_SHARE_TOKEN_RESPONSE,
                response_dict['payload'],
                request_id=message.request_id
            )
    
    # Notification handlers (auth required)
    
    def _handle_subscribe_room(self, connection: SocketConnection, message: Message) -> None:
        """Handle SUBSCRIBE_ROOM request."""
        try:
            self.notification_handlers.handle_subscribe_room(connection, message)
        except Exception as e:
            logger.error(f"Error handling SUBSCRIBE_ROOM: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_unsubscribe_room(self, connection: SocketConnection, message: Message) -> None:
        """Handle UNSUBSCRIBE_ROOM request."""
        try:
            self.notification_handlers.handle_unsubscribe_room(connection, message)
        except Exception as e:
            logger.error(f"Error handling UNSUBSCRIBE_ROOM: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    # Health check handlers (no auth required)
    
    def _handle_ping(self, connection: SocketConnection, message: Message) -> None:
        """Handle PING request."""
        try:
            self.health_handlers.handle_ping(connection, message)
        except Exception as e:
            logger.error(f"Error handling PING: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_status(self, connection: SocketConnection, message: Message) -> None:
        """Handle STATUS request."""
        try:
            self.health_handlers.handle_status(connection, message)
        except Exception as e:
            logger.error(f"Error handling STATUS: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    # Helper methods
    
    def _handle_authenticated_request(
        self,
        connection: SocketConnection,
        message: Message,
        handler: Callable[[Message, Dict], Message]
    ) -> None:
        """
        Handle a request that requires authentication.
        
        Args:
            connection: Socket connection
            message: Incoming message
            handler: Handler function that takes (message, context) and returns response Message
        """
        try:
            # Validate authentication
            valid, context, error_msg = self.auth_middleware.validate_request(message)
            
            if not valid:
                connection.send_message(error_msg)
                return
            
            # Call handler with context
            response = handler(message, context)
            connection.send_message(response)
        
        except Exception as e:
            logger.error(f"Error handling authenticated request: {e}", exc_info=True)
            error_msg = Message.create_error(
                "INTERNAL_ERROR",
                "An internal error occurred",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _on_connection_closed(self, connection: SocketConnection) -> None:
        """
        Called when a connection is closed.
        Clean up notification subscriptions.
        
        Args:
            connection: Closed connection
        """
        try:
            # Remove connection from all notification subscriptions
            self.notification_service.remove_subscriber_from_all_rooms(connection)
            legacy_cleanup = getattr(self.notification_service, "remove_connection", None)
            if callable(legacy_cleanup):
                legacy_cleanup(connection)
            logger.info(f"Cleaned up subscriptions for connection {connection.connection_id}")
        except Exception as e:
            logger.error(f"Error cleaning up connection {connection.connection_id}: {e}")
