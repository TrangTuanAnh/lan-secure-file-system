"""Storage Node socket server for persistent connections."""
import time
import threading
from typing import Optional
from datetime import datetime, timezone
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType
from ticket.ticket_service import TicketService
from upload.upload_service import UploadService
from storage_node.registry import StorageNodeInfo, StorageNodeRegistry
from logging_config import get_logger

logger = get_logger(__name__)


class StorageNodeServer(BaseSocketServer):
    """
    Socket server for Storage Node communication.
    
    Handles:
    - Authentication via shared secret
    - Heartbeat (PING/PONG)
    - Ticket verification (VERIFY_TICKET)
    - Upload completion notifications (UPLOAD_COMPLETE, UPLOAD_FAILED)
    
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        shared_secret: str,
        ticket_service: TicketService,
        upload_service: UploadService,
        timeout_seconds: int = 90,
        registry: Optional[StorageNodeRegistry] = None
    ):
        """
        Initialize Storage Node server.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            shared_secret: Shared secret for authentication
            ticket_service: Ticket service for verification
            upload_service: Upload service for completion handling
            timeout_seconds: Timeout for marking nodes unavailable (default 90s)
            registry: Shared storage node registry used for load balancing
        """
        super().__init__(host, port, name="StorageNodeServer")
        
        self.shared_secret = shared_secret
        self.ticket_service = ticket_service
        self.upload_service = upload_service
        self.timeout_seconds = timeout_seconds
        self.registry = registry or StorageNodeRegistry(timeout_seconds=timeout_seconds)
        
        # Health check thread
        self._health_check_thread: Optional[threading.Thread] = None
        self._health_check_running = False
        
        # Register message handlers
        self._register_handlers()
        
        logger.info(
            f"StorageNodeServer initialized on {host}:{port}, "
            f"timeout={timeout_seconds}s"
        )
    
    def _register_handlers(self) -> None:
        """Register message handlers for Storage Node communication."""
        self.register_handler(MessageType.STORAGE_AUTH, self._handle_storage_auth)
        self.register_handler(MessageType.PING, self._handle_ping)
        self.register_handler(MessageType.VERIFY_TICKET, self._handle_verify_ticket)
        self.register_handler(MessageType.UPLOAD_COMPLETE, self._handle_upload_complete)
        self.register_handler(MessageType.UPLOAD_FAILED, self._handle_upload_failed)
    
    def start(self) -> None:
        """Start the server and health check thread."""
        super().start()
        
        # Start health check thread
        self._health_check_running = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )
        self._health_check_thread.start()
        
        logger.info("StorageNodeServer health check started")
    
    def stop(self) -> None:
        """Stop the server and health check thread."""
        # Stop health check
        self._health_check_running = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5.0)
        
        super().stop()
    
    def _on_connection_established(self, connection: SocketConnection) -> None:
        """
        Called when a new connection is established.
        
        Args:
            connection: Newly established connection
        """
        self.registry.add_connection(connection)
        
        logger.info(f"Storage Node connection established: {connection.connection_id}")
    
    def _on_connection_closed(self, connection: SocketConnection) -> None:
        """
        Called when a connection is closed.
        
        Args:
            connection: Closed connection
        """
        node_info = self.registry.remove_connection(connection)
        
        if node_info:
            logger.info(
                f"Storage Node disconnected: {node_info.node_id}, "
                f"authenticated={node_info.authenticated}"
            )
    
    def _handle_storage_auth(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle STORAGE_AUTH message.
        
        Requirements: 10.2
        
        Args:
            connection: Connection that sent the message
            message: STORAGE_AUTH message with payload: {"secret": "..."}
        """
        secret = message.payload.get('secret')
        
        if not secret:
            logger.warning(f"STORAGE_AUTH missing secret from {connection.connection_id}")
            error_msg = Message.create_error(
                "MISSING_SECRET",
                "Authentication secret is required",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        # Verify shared secret
        if secret != self.shared_secret:
            logger.warning(f"STORAGE_AUTH invalid secret from {connection.connection_id}")
            error_msg = Message.create_error(
                "INVALID_SECRET",
                "Authentication failed: invalid secret",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        node_id = message.payload.get('nodeId') or connection.connection_id
        data_host = message.payload.get('dataHost')
        data_port = message.payload.get('dataPort')
        storage_address = message.payload.get('storageAddress')

        if not data_host:
            address = getattr(connection, 'address', None)
            if address:
                data_host = address[0]

        if data_port is not None:
            try:
                data_port = int(data_port)
            except (TypeError, ValueError):
                logger.warning(
                    f"STORAGE_AUTH invalid dataPort from {connection.connection_id}: {data_port}"
                )
                error_msg = Message.create_error(
                    "INVALID_DATA_PORT",
                    "dataPort must be an integer",
                    request_id=message.request_id
                )
                connection.send_message(error_msg)
                return

        node_info = self.registry.authenticate(
            connection=connection,
            node_id=node_id,
            data_host=data_host,
            data_port=data_port,
            storage_address=storage_address
        )

        logger.info(
            f"Storage Node authenticated: node_id={node_info.node_id}, "
            f"storageAddress={node_info.storage_address}"
        )
        
        # Send success response
        response = Message.create_response(
            MessageType.STORAGE_AUTH_RESPONSE,
            {"status": "authenticated", "nodeId": node_info.node_id},
            request_id=message.request_id
        )
        connection.send_message(response)
    
    def _handle_ping(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle PING message and respond with PONG.
        
        Requirements: 10.3
        
        Args:
            connection: Connection that sent the message
            message: PING message
        """
        node_info = self.registry.get_by_connection(connection)
        if not node_info or not node_info.authenticated:
            logger.warning(f"PING from unauthenticated node: {connection.connection_id}")
            error_msg = Message.create_error(
                "NOT_AUTHENTICATED",
                "Must authenticate before sending PING",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return

        self.registry.heartbeat(connection)
        
        logger.debug(f"PING received from {connection.connection_id}")
        
        # Respond with PONG
        pong = Message.create_response(
            MessageType.PONG,
            {"timestamp": datetime.now(timezone.utc).isoformat()},
            request_id=message.request_id
        )
        connection.send_message(pong)
    
    def _handle_verify_ticket(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle VERIFY_TICKET message.
        
        Requirements: 10.5
        
        Args:
            connection: Connection that sent the message
            message: VERIFY_TICKET message with payload: {"ticket": "..."}
        """
        node_info = self.registry.get_by_connection(connection)
        if not node_info or not node_info.authenticated:
            logger.warning(f"VERIFY_TICKET from unauthenticated node: {connection.connection_id}")
            error_msg = Message.create_error(
                "NOT_AUTHENTICATED",
                "Must authenticate before verifying tickets",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        ticket_id = message.payload.get('ticket')
        
        if not ticket_id:
            logger.warning(f"VERIFY_TICKET missing ticket from {connection.connection_id}")
            error_msg = Message.create_error(
                "MISSING_TICKET",
                "Ticket ID is required",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        # Verify ticket using ticket service
        is_valid, ticket_data, error_code = self.ticket_service.verify_ticket(ticket_id)
        
        if is_valid:
            logger.info(f"Ticket verified: {ticket_id}, type={ticket_data.get('type')}")
            
            # Send TICKET_VALID response with metadata
            response = Message.create_response(
                MessageType.TICKET_VALID,
                ticket_data,
                request_id=message.request_id
            )
            connection.send_message(response)
        else:
            logger.info(f"Ticket verification failed: {ticket_id}, error={error_code}")
            
            # Send TICKET_INVALID response
            response = Message.create_response(
                MessageType.TICKET_INVALID,
                {"error": error_code},
                request_id=message.request_id
            )
            connection.send_message(response)
    
    def _handle_upload_complete(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle UPLOAD_COMPLETE message.
        
        Requirements: 10.6
        
        Args:
            connection: Connection that sent the message
            message: UPLOAD_COMPLETE message with payload:
                {
                    "fileId": "...",
                    "sha256Whole": "...",
                    "storedName": "...",
                    "finalSize": 12345
                }
        """
        node_info = self.registry.get_by_connection(connection)
        if not node_info or not node_info.authenticated:
            logger.warning(f"UPLOAD_COMPLETE from unauthenticated node: {connection.connection_id}")
            error_msg = Message.create_error(
                "NOT_AUTHENTICATED",
                "Must authenticate before sending notifications",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        # Extract payload
        file_id = message.payload.get('fileId')
        sha256_whole = message.payload.get('sha256Whole')
        stored_name = message.payload.get('storedName')
        final_size = message.payload.get('finalSize')
        
        # Validate required fields
        if not all([file_id, sha256_whole, stored_name, final_size is not None]):
            logger.warning(f"UPLOAD_COMPLETE missing required fields from {connection.connection_id}")
            error_msg = Message.create_error(
                "INVALID_PAYLOAD",
                "Missing required fields: fileId, sha256Whole, storedName, finalSize",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        logger.info(
            f"UPLOAD_COMPLETE received: file_id={file_id}, "
            f"size={final_size}, from={connection.connection_id}"
        )
        
        # Route to upload service
        success, error_code = self.upload_service.handle_upload_complete(
            file_id=file_id,
            sha256_whole=sha256_whole,
            stored_name=stored_name,
            final_size=final_size,
            storage_node_id=node_info.node_id
        )
        
        if success:
            # Send ACK
            ack = Message.create_response(
                MessageType.ACK,
                {"status": "success"},
                request_id=message.request_id
            )
            connection.send_message(ack)
        else:
            # Send error response
            error_msg = Message.create_error(
                error_code or "INTERNAL_ERROR",
                f"Failed to process upload completion: {error_code}",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _handle_upload_failed(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle UPLOAD_FAILED message.
        
        Requirements: 10.7
        
        Args:
            connection: Connection that sent the message
            message: UPLOAD_FAILED message with payload:
                {
                    "fileId": "...",
                    "reason": "..."
                }
        """
        node_info = self.registry.get_by_connection(connection)
        if not node_info or not node_info.authenticated:
            logger.warning(f"UPLOAD_FAILED from unauthenticated node: {connection.connection_id}")
            error_msg = Message.create_error(
                "NOT_AUTHENTICATED",
                "Must authenticate before sending notifications",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        # Extract payload
        file_id = message.payload.get('fileId')
        reason = message.payload.get('reason', 'Unknown error')
        
        if not file_id:
            logger.warning(f"UPLOAD_FAILED missing fileId from {connection.connection_id}")
            error_msg = Message.create_error(
                "INVALID_PAYLOAD",
                "Missing required field: fileId",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return
        
        logger.warning(
            f"UPLOAD_FAILED received: file_id={file_id}, "
            f"reason={reason}, from={connection.connection_id}"
        )
        
        # Route to upload service
        success, error_code = self.upload_service.handle_upload_failed(
            file_id=file_id,
            reason=reason,
            storage_node_id=node_info.node_id
        )
        
        if success:
            # Send ACK
            ack = Message.create_response(
                MessageType.ACK,
                {"status": "success"},
                request_id=message.request_id
            )
            connection.send_message(ack)
        else:
            # Send error response
            error_msg = Message.create_error(
                error_code or "INTERNAL_ERROR",
                f"Failed to process upload failure: {error_code}",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
    
    def _health_check_loop(self) -> None:
        """
        Periodic health check loop.
        
        Requirements: 10.4
        
        Runs every 30 seconds and marks nodes as unavailable if no PING
        received within timeout period.
        """
        logger.info("Storage Node health check loop started")
        
        while self._health_check_running:
            try:
                # Sleep for 30 seconds
                time.sleep(30)
                
                if not self._health_check_running:
                    break
                
                unhealthy_nodes = [
                    (node_info.connection, node_info)
                    for node_info in self.registry.get_all_nodes()
                    if node_info.authenticated and not node_info.is_healthy(self.timeout_seconds)
                ]
                
                # Close unhealthy connections
                for connection, node_info in unhealthy_nodes:
                    logger.warning(
                        f"Storage Node timeout: {node_info.node_id}, "
                        f"last_ping={node_info.last_ping_time:.0f}, "
                        f"timeout={self.timeout_seconds}s"
                    )
                    
                    try:
                        connection.close()
                    except Exception as e:
                        logger.error(f"Error closing unhealthy connection: {e}")
            
            except Exception as e:
                logger.error(f"Health check loop error: {e}", exc_info=True)
        
        logger.info("Storage Node health check loop stopped")
    
    def get_connected_nodes(self) -> list:
        """
        Get list of connected and authenticated Storage Nodes.
        
        Returns:
            List of node info dictionaries
        """
        return self.registry.get_connected_nodes()
