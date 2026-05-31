"""Base socket server with connection management."""
import socket
import ssl
import select
import threading
import selectors
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Callable, Any
from protocol.frame_codec import FrameCodec, FrameBuffer
from protocol.message import Message
from protocol.message_types import MessageType
from logging_config import get_logger

logger = get_logger(__name__)


class SocketConnection:
    """
    Represents a single socket connection with frame buffering.
    """

    def __init__(self, sock: socket.socket, address: tuple):
        """
        Initialize connection.

        Args:
            sock: Connected socket
            address: Remote address (host, port)
        """
        self.socket = sock
        self.address = address
        self.buffer = FrameBuffer()
        self.connection_id = f"{address[0]}:{address[1]}"

        # Request-response tracking
        self.pending_requests: Dict[str, Any] = {}

        # Protects socket.sendall — multiple worker threads can call
        # send_message on the same connection concurrently.
        self._send_lock = threading.Lock()
        self._closed = False

        logger.info(f"New connection: {self.connection_id}")

    def send_message(self, message: Message) -> None:
        """
        Send a message over this connection.

        Args:
            message: Message to send

        Raises:
            OSError: If socket send fails
        """
        # Serialize message to bytes
        message_bytes = message.to_bytes()

        # Encode with length prefix
        frame = FrameCodec.encode(message_bytes)

        with self._send_lock:
            if self._closed:
                logger.debug(f"Skip send to closed connection {self.connection_id}")
                return
            self._sendall(frame)
        logger.debug(f"Sent message to {self.connection_id}: type={message.type.value}, size={len(message_bytes)}")

    def _sendall(self, data: bytes) -> None:
        """
        Send all bytes, transparently handling TLS on non-blocking sockets.

        Plaintext sockets keep the original behaviour. For a non-blocking
        ``SSLSocket`` a write may raise ``SSLWantWriteError``/``SSLWantReadError``
        mid-record; per the OpenSSL contract we wait for readiness and retry the
        write with the same buffer.
        """
        sock = self.socket
        if not isinstance(sock, ssl.SSLSocket):
            sock.sendall(data)
            return
        while True:
            try:
                sock.sendall(data)
                return
            except ssl.SSLWantWriteError:
                select.select([], [sock], [], 5)
            except ssl.SSLWantReadError:
                select.select([sock], [], [], 5)
    
    def receive_data(self, chunk_size: int = 4096) -> Optional[bytes]:
        """
        Receive data from socket.
        
        Args:
            chunk_size: Maximum bytes to receive
        
        Returns:
            Received data, or None if connection closed
        
        Raises:
            OSError: If socket receive fails
        """
        try:
            data = self.socket.recv(chunk_size)
            if not data:
                # Connection closed by peer
                return None
            return data
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError):
            # Non-blocking TLS: a full record isn't available yet. Not an error
            # and not EOF — signal "no data right now" with an empty buffer.
            return b''
        except ssl.SSLEOFError:
            # TLS peer closed (possibly uncleanly) — treat as connection closed.
            return None
        except ConnectionError:
            # Peer went away (broken pipe / reset), e.g. a health probe that
            # connects then immediately closes. Treat as a normal close.
            return None
        except socket.error as e:
            logger.error(f"Socket error on {self.connection_id}: {e}")
            raise
    
    def close(self) -> None:
        """Close the connection."""
        with self._send_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.socket.close()
                logger.info(f"Connection closed: {self.connection_id}")
            except Exception as e:
                logger.error(f"Error closing connection {self.connection_id}: {e}")


class BaseSocketServer:
    """
    Base socket server with connection management and message handling.
    
    This class provides:
    - Accept incoming connections
    - Manage multiple concurrent connections
    - Frame-based message encoding/decoding
    - Message routing to handlers
    - Request-response matching using requestId
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        name: str = "SocketServer",
        max_workers: int = 8,
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        """
        Initialize socket server.

        Args:
            host: Host to bind to
            port: Port to bind to
            name: Server name for logging
            max_workers: Worker pool size for handler dispatch
            ssl_context: Optional server-side SSLContext. When provided, every
                accepted connection is wrapped in TLS. Leave None for plaintext
                (e.g. the internal storage-node control plane).
        """
        self.host = host
        self.port = port
        self.name = name
        self.max_workers = max_workers
        self._ssl_context = ssl_context
        self._tls_handshake_timeout = 15.0

        self._server_socket: Optional[socket.socket] = None
        self._selector = selectors.DefaultSelector()
        self._connections: Dict[socket.socket, SocketConnection] = {}
        self._connections_lock = threading.Lock()
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None

        # Message handlers: MessageType -> handler function
        self._handlers: Dict[MessageType, Callable[[SocketConnection, Message], None]] = {}

        logger.info(
            f"{self.name} initialized on {host}:{port} "
            f"(max_workers={max_workers}, tls={'on' if ssl_context else 'off'})"
        )
    
    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[SocketConnection, Message], None]
    ) -> None:
        """
        Register a message handler.
        
        Args:
            message_type: Type of message to handle
            handler: Handler function(connection, message)
        """
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type.value}")
    
    def start(self) -> None:
        """Start the server in a background thread."""
        if self._running:
            logger.warning(f"{self.name} already running")
            return

        # Create server socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(100)
        self._server_socket.setblocking(False)

        # Register server socket for accept events
        self._selector.register(self._server_socket, selectors.EVENT_READ, data=None)

        # Worker pool for handler dispatch (producer-consumer pattern)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=f"{self.name}-Worker",
        )

        self._running = True
        self._server_thread = threading.Thread(
            target=self._run_loop, name=f"{self.name}-Acceptor", daemon=True
        )
        self._server_thread.start()

        logger.info(f"{self.name} started on {self.host}:{self.port}")
    
    def stop(self) -> None:
        """Stop the server and close all connections."""
        if not self._running:
            return

        logger.info(f"Stopping {self.name}...")
        self._running = False

        # Close all client connections
        with self._connections_lock:
            for conn in list(self._connections.values()):
                conn.close()
            self._connections.clear()

        # Close server socket
        if self._server_socket:
            try:
                self._selector.unregister(self._server_socket)
            except Exception:
                pass
            self._server_socket.close()

        # Close selector
        self._selector.close()

        # Wait for server thread
        if self._server_thread:
            self._server_thread.join(timeout=5.0)

        # Drain worker pool (wait for in-flight handlers)
        if self._executor:
            self._executor.shutdown(wait=True)

        logger.info(f"{self.name} stopped")
    
    def _run_loop(self) -> None:
        """Main event loop (runs in background thread)."""
        logger.info(f"{self.name} event loop started")
        
        try:
            while self._running:
                # Wait for events with timeout
                events = self._selector.select(timeout=1.0)
                
                for key, mask in events:
                    if key.data is None:
                        # Server socket - accept new connection
                        self._accept_connection()
                    else:
                        # Client socket - read data
                        self._handle_client_data(key.fileobj)
        except Exception as e:
            logger.error(f"{self.name} event loop error: {e}", exc_info=True)
        finally:
            logger.info(f"{self.name} event loop stopped")
    
    def _accept_connection(self) -> None:
        """Accept a new client connection."""
        try:
            client_socket, address = self._server_socket.accept()

            if self._ssl_context is not None:
                # Perform the TLS handshake in blocking mode (bounded by a
                # timeout so a stalled peer can't hang the acceptor), then drop
                # back to non-blocking for the selector-driven read loop.
                try:
                    client_socket.settimeout(self._tls_handshake_timeout)
                    client_socket = self._ssl_context.wrap_socket(
                        client_socket, server_side=True
                    )
                except (ssl.SSLError, OSError) as e:
                    logger.warning(f"{self.name} TLS handshake failed from {address}: {e}")
                    try:
                        client_socket.close()
                    except Exception:
                        pass
                    return

            client_socket.setblocking(False)

            # Create connection object
            connection = SocketConnection(client_socket, address)
            with self._connections_lock:
                self._connections[client_socket] = connection

            # Register for read events
            self._selector.register(client_socket, selectors.EVENT_READ, data=connection)

            logger.info(f"{self.name} accepted connection from {connection.connection_id}")

            # Call connection callback if implemented
            self._on_connection_established(connection)

        except Exception as e:
            logger.error(f"{self.name} error accepting connection: {e}")
    
    def _handle_client_data(self, sock: socket.socket) -> None:
        """
        Handle data from a client socket.

        Args:
            sock: Client socket with data ready
        """
        with self._connections_lock:
            connection = self._connections.get(sock)
        if not connection:
            logger.warning(f"Received data from unknown socket")
            return

        try:
            # A single selector readiness event maps to one TCP read for plain
            # sockets. For TLS, one TCP segment can carry several records that
            # the SSL layer buffers internally; the selector won't fire again
            # for those, so we loop while pending() reports buffered bytes.
            while True:
                data = connection.receive_data()

                if data is None:
                    # Connection closed by peer
                    self._close_connection(sock)
                    return

                if data:
                    connection.buffer.append(data)
                    self._process_buffer(connection)

                sock_obj = connection.socket
                if isinstance(sock_obj, ssl.SSLSocket) and sock_obj.pending() > 0:
                    continue
                return

        except Exception as e:
            logger.error(f"Error handling data from {connection.connection_id}: {e}", exc_info=True)
            self._close_connection(sock)

    def _process_buffer(self, connection: SocketConnection) -> None:
        """Extract and dispatch all complete frames currently in the buffer."""
        while True:
            frame = connection.buffer.extract_frame()
            if frame is None:
                break

            # Deserialize message
            try:
                message = Message.from_bytes(frame)
                self._dispatch_message(connection, message)
            except ValueError as e:
                logger.error(f"Invalid message from {connection.connection_id}: {e}")
                # Send error response
                error_msg = Message.create_error(
                    "INVALID_MESSAGE",
                    f"Failed to parse message: {e}"
                )
                connection.send_message(error_msg)
    
    def _dispatch_message(self, connection: SocketConnection, message: Message) -> None:
        """
        Dispatch message to appropriate handler.

        The acceptor thread only enqueues; the actual handler runs on a
        worker thread from the pool. This is the producer-consumer split
        that keeps slow handlers from blocking other clients' I/O.

        Args:
            connection: Connection that received the message
            message: Parsed message
        """
        logger.debug(f"Received message from {connection.connection_id}: type={message.type.value}")

        handler = self._handlers.get(message.type)

        if handler is None:
            logger.warning(f"No handler for message type: {message.type.value}")
            error_msg = Message.create_error(
                "UNKNOWN_MESSAGE_TYPE",
                f"Unknown message type: {message.type.value}",
                request_id=message.request_id
            )
            connection.send_message(error_msg)
            return

        if self._executor is None:
            # Fallback: run synchronously (e.g. server not started via start())
            self._run_handler(handler, connection, message)
            return

        self._executor.submit(self._run_handler, handler, connection, message)

    def _run_handler(
        self,
        handler: Callable[[SocketConnection, Message], None],
        connection: SocketConnection,
        message: Message,
    ) -> None:
        """Execute a handler on a worker thread with error isolation."""
        try:
            handler(connection, message)
        except Exception as e:
            logger.error(
                f"Handler error for {message.type.value} from {connection.connection_id}: {e}",
                exc_info=True
            )
            try:
                error_msg = Message.create_error(
                    "INTERNAL_ERROR",
                    "An internal error occurred while processing your request",
                    request_id=message.request_id
                )
                connection.send_message(error_msg)
            except Exception as send_err:
                logger.error(f"Failed to send error response: {send_err}")
    
    def _close_connection(self, sock: socket.socket) -> None:
        """
        Close a client connection.

        Args:
            sock: Client socket to close
        """
        with self._connections_lock:
            connection = self._connections.pop(sock, None)
        if not connection:
            return

        try:
            # Unregister from selector
            self._selector.unregister(sock)
        except Exception:
            pass

        # Close connection
        connection.close()

        # Call disconnection callback if implemented
        self._on_connection_closed(connection)
    
    def _on_connection_established(self, connection: SocketConnection) -> None:
        """
        Called when a new connection is established.
        Override in subclasses for custom behavior.
        
        Args:
            connection: Newly established connection
        """
        pass
    
    def _on_connection_closed(self, connection: SocketConnection) -> None:
        """
        Called when a connection is closed.
        Override in subclasses for custom behavior.
        
        Args:
            connection: Closed connection
        """
        pass
    
    def get_connection_count(self) -> int:
        """
        Get number of active connections.

        Returns:
            Number of connections
        """
        with self._connections_lock:
            return len(self._connections)
