"""Storage Node socket server for persistent connections."""
import time
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType
from ticket.ticket_service import TicketService
from upload.upload_service import UploadService
from storage_node.registry import StorageNodeInfo, StorageNodeRegistry
from storage_node.reconciliation_service import ReconciliationService
from audit.audit_service import AuditService
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
        registry: Optional[StorageNodeRegistry] = None,
        reconciliation_service: Optional[ReconciliationService] = None,
        audit_service: Optional[AuditService] = None,
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
            audit_service: Optional audit log writer. When provided, storage-node
                authentication attempts and disconnects are recorded.
        """
        super().__init__(host, port, name="StorageNodeServer")

        self.shared_secret = shared_secret
        self.ticket_service = ticket_service
        self.upload_service = upload_service
        self.timeout_seconds = timeout_seconds
        self.registry = registry or StorageNodeRegistry(timeout_seconds=timeout_seconds)
        self.reconciliation_service = reconciliation_service
        self.audit_service = audit_service
        
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
        self.register_handler(MessageType.MANIFEST_DELTA, self._handle_manifest_delta)
    
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

    def get_connected_nodes(self) -> List[Dict[str, Any]]:
        """Return authenticated storage nodes with computed health metadata."""
        return self.registry.get_connected_nodes()

    def _health_check_loop(self) -> None:
        """
        Periodically inspect node health and log stale connections.

        The registry already computes node health from last heartbeat, so this
        loop stays read-only and avoids changing upload/download behavior.
        """
        check_interval = max(1, min(30, self.timeout_seconds // 3 or 1))
        warned_unhealthy: set[str] = set()

        while self._health_check_running:
            try:
                nodes = self.registry.get_all_nodes()
                current_unhealthy: set[str] = set()

                for node in nodes:
                    if node.authenticated and not node.is_healthy(self.timeout_seconds):
                        current_unhealthy.add(node.node_id)
                        if node.node_id not in warned_unhealthy:
                            age_seconds = max(0.0, time.time() - node.last_ping_time)
                            logger.warning(
                                "Storage Node heartbeat timed out: node_id=%s "
                                "last_ping_age=%.1fs timeout=%ss",
                                node.node_id,
                                age_seconds,
                                self.timeout_seconds,
                            )

                warned_unhealthy = current_unhealthy
            except Exception as exc:
                logger.error(f"StorageNodeServer health check loop failed: {exc}", exc_info=True)

            time.sleep(check_interval)
    
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
            # BUGFIX (audit): log storage-node disconnects so the operator can
            # correlate "node went away" with subsequent upload failures.
            if self.audit_service and node_info.authenticated:
                try:
                    self.audit_service.write_audit_log(
                        actor_id=None,
                        action='STORAGE_NODE_DISCONNECT',
                        target_type='storage_node',
                        target_id=node_info.node_id,
                        room_id=None,
                        detail={
                            'storage_address': node_info.storage_address,
                            'connection_id': connection.connection_id,
                        },
                        status='SUCCESS'
                    )
                except Exception as e:
                    logger.error(f"Failed to write disconnect audit log: {e}")

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
        candidate_node_id = message.payload.get('nodeId') or connection.connection_id

        if not secret:
            logger.warning(f"STORAGE_AUTH missing secret from {connection.connection_id}")
            # BUGFIX (audit): record failed authentication attempts so admin
            # can spot brute-force / misconfigured nodes.
            if self.audit_service:
                try:
                    self.audit_service.write_audit_log(
                        actor_id=None,
                        action='STORAGE_NODE_AUTH',
                        target_type='storage_node',
                        target_id=str(candidate_node_id),
                        room_id=None,
                        detail={
                            'reason': 'MISSING_SECRET',
                            'connection_id': connection.connection_id,
                        },
                        status='FAILED'
                    )
                except Exception:
                    pass
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
            if self.audit_service:
                try:
                    self.audit_service.write_audit_log(
                        actor_id=None,
                        action='STORAGE_NODE_AUTH',
                        target_type='storage_node',
                        target_id=str(candidate_node_id),
                        room_id=None,
                        detail={
                            'reason': 'INVALID_SECRET',
                            'connection_id': connection.connection_id,
                        },
                        status='FAILED'
                    )
                except Exception:
                    pass
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

        # BUGFIX (audit): record successful storage-node authentication.
        if self.audit_service:
            try:
                self.audit_service.write_audit_log(
                    actor_id=None,
                    action='STORAGE_NODE_AUTH',
                    target_type='storage_node',
                    target_id=str(node_info.node_id),
                    room_id=None,
                    detail={
                        'storage_address': node_info.storage_address,
                        'data_host': data_host,
                        'data_port': data_port,
                        'connection_id': connection.connection_id,
                    },
                    status='SUCCESS'
                )
            except Exception as e:
                logger.error(f"Failed to write STORAGE_NODE_AUTH audit log: {e}")

        manifest = message.payload.get('manifest')
        if isinstance(manifest, list):
            normalized = self.registry.set_manifest(node_info.node_id, manifest)
            logger.info(
                f"Storage Node manifest received: node_id={node_info.node_id}, "
                f"count={len(normalized) if normalized is not None else 0}"
            )
            if self.reconciliation_service and normalized is not None:
                try:
                    self.reconciliation_service.reconcile_node(node_info.node_id, normalized)
                except Exception as e:
                    logger.error(
                        f"Reconciliation failed for node {node_info.node_id}: {e}",
                        exc_info=True
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
            # Treat completion as implicit manifest add: the node's MANIFEST_DELTA
            # for this sha may race after the ACK, and we don't want a download
            # in between to see the node as 'not holding' the file it just stored.
            self.registry.mark_file_added(node_info.node_id, sha256_whole)
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

    def _handle_manifest_delta(
        self,
        connection: SocketConnection,
        message: Message
    ) -> None:
        """
        Handle MANIFEST_DELTA message.

        Storage Nodes send incremental sha256 additions/removals after the
        initial manifest snapshot included in STORAGE_AUTH.

        Args:
            connection: Connection that sent the message
            message: MANIFEST_DELTA message with payload:
                {
                    "added": ["sha256-1", ...],
                    "removed": ["sha256-2", ...]
                }
        """
        node_info = self.registry.get_by_connection(connection)
        if not node_info or not node_info.authenticated:
            logger.warning(f"MANIFEST_DELTA from unauthenticated node: {connection.connection_id}")
            error_msg = Message.create_error(
                "NOT_AUTHENTICATED",
                "Must authenticate before sending MANIFEST_DELTA",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return

        added = message.payload.get('added', [])
        removed = message.payload.get('removed', [])

        if added is None:
            added = []
        if removed is None:
            removed = []

        if not isinstance(added, list) or not isinstance(removed, list):
            logger.warning(
                f"MANIFEST_DELTA invalid payload from {connection.connection_id}: "
                f"added_type={type(added).__name__}, removed_type={type(removed).__name__}"
            )
            error_msg = Message.create_error(
                "INVALID_PAYLOAD",
                "MANIFEST_DELTA requires list fields: added, removed",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return

        applied = self.registry.apply_manifest_delta(
            node_info.node_id,
            added=added,
            removed=removed,
        )
        if not applied:
            logger.warning(
                f"MANIFEST_DELTA could not be applied: node_id={node_info.node_id}, "
                f"connection={connection.connection_id}"
            )
            error_msg = Message.create_error(
                "NODE_NOT_FOUND",
                "Failed to apply manifest delta for storage node",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return

        logger.info(
            f"MANIFEST_DELTA applied: node_id={node_info.node_id}, "
            f"added={len(added)}, removed={len(removed)}"
        )

        ack = Message.create_response(
            MessageType.ACK,
            {"status": "success"},
            request_id=message.request_id
        )
        connection.send_message(ack)

