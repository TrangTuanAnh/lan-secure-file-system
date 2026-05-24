"""
Production-ready Python TCP socket client for Coordinator Server.

Thread-safe, handles reconnection, implements frame codec protocol.
"""

import socket
import struct
import json
import uuid
import threading
import time
import logging
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class BackendConfig:
    """Configuration for backend connection."""
    host: str = "localhost"
    port: int = 8080
    timeout: int = 30  # seconds per request
    socket_timeout: int = 5  # socket-level timeout
    max_retries: int = 3
    retry_delay: int = 2  # seconds
    frame_max_size: int = 10 * 1024 * 1024  # 10MB
    

class FrameCodec:
    """Codec for length-prefixed frame format."""
    
    HEADER_SIZE = 4
    HEADER_FORMAT = '!I'  # Network byte order (big-endian), unsigned int
    
    @staticmethod
    def encode(message: bytes) -> bytes:
        """Encode message with 4-byte length prefix."""
        message_length = len(message)
        header = struct.pack(FrameCodec.HEADER_FORMAT, message_length)
        return header + message
    
    @staticmethod
    def decode_header(data: bytes) -> Optional[int]:
        """Decode message length from frame header."""
        if len(data) < FrameCodec.HEADER_SIZE:
            return None
        message_length = struct.unpack(FrameCodec.HEADER_FORMAT, 
                                      data[:FrameCodec.HEADER_SIZE])[0]
        return message_length
    
    @staticmethod
    def decode_frame(data: bytes) -> Tuple[Optional[bytes], int]:
        """Extract complete frame from buffer."""
        if len(data) < FrameCodec.HEADER_SIZE:
            return None, 0
        
        message_length = FrameCodec.decode_header(data)
        if message_length is None:
            return None, 0
        
        total_frame_size = FrameCodec.HEADER_SIZE + message_length
        
        if len(data) < total_frame_size:
            return None, 0
        
        message = data[FrameCodec.HEADER_SIZE:total_frame_size]
        return message, total_frame_size


class FrameBuffer:
    """Buffer for accumulating incoming data and extracting frames."""
    
    def __init__(self):
        self._buffer = bytearray()
    
    def append(self, data: bytes) -> None:
        """Append data to buffer."""
        self._buffer.extend(data)
    
    def extract_frame(self) -> Optional[bytes]:
        """Extract one complete frame from buffer."""
        if len(self._buffer) < FrameCodec.HEADER_SIZE:
            return None
        
        message, bytes_consumed = FrameCodec.decode_frame(bytes(self._buffer))
        
        if message is not None:
            del self._buffer[:bytes_consumed]
        
        return message
    
    def clear(self) -> None:
        """Clear buffer."""
        self._buffer.clear()


class BackendConnectionException(Exception):
    """Exception for backend connection errors."""
    pass


class BackendClient:
    """
    Thread-safe TCP socket client for Coordinator Server.
    
    Features:
    - Connection pooling and reconnection logic
    - Frame codec protocol (4-byte length prefix + JSON)
    - Request-response matching via requestId
    - Token management
    - Background message listener thread
    - Event subscription support
    - Timeout handling
    """
    
    def __init__(self, config: BackendConfig = None):
        """
        Initialize backend client.
        
        Args:
            config: BackendConfig instance
        """
        self.config = config or BackendConfig()
        
        # Connection state
        self._socket: Optional[socket.socket] = None
        self._state = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()
        
        # Buffers and queues
        self._frame_buffer = FrameBuffer()
        self._socket_lock = threading.Lock()
        
        # Request-response matching
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._pending_lock = threading.Lock()
        
        # Background listener thread
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Token storage
        self._token: Optional[str] = None
        self._token_lock = threading.Lock()
        
        # Event handlers
        self._event_callbacks: Dict[str, List[Callable]] = {}
        self._callbacks_lock = threading.Lock()
        
        logger.info(f"Initialized BackendClient for {self.config.host}:{self.config.port}")
    
    # ==================== Connection Management ====================
    
    def connect(self) -> bool:
        """
        Connect to backend server.
        
        Returns:
            True if connected, False otherwise
        """
        if self._state == ConnectionState.CONNECTED:
            logger.warning("Already connected")
            return True
        
        self._set_state(ConnectionState.CONNECTING)
        
        for attempt in range(self.config.max_retries):
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.config.socket_timeout)
                self._socket.connect((self.config.host, self.config.port))
                
                # Start listener thread
                if not self._running:
                    self._running = True
                    self._listener_thread = threading.Thread(
                        target=self._listen_loop,
                        daemon=True
                    )
                    self._listener_thread.start()
                
                self._set_state(ConnectionState.CONNECTED)
                logger.info(f"Connected to {self.config.host}:{self.config.port}")
                return True
            
            except socket.timeout:
                logger.warning(f"Connection timeout on attempt {attempt + 1}/{self.config.max_retries}")
                self._cleanup_socket()
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
            
            except Exception as e:
                logger.error(f"Connection error on attempt {attempt + 1}/{self.config.max_retries}: {e}")
                self._cleanup_socket()
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
        
        self._set_state(ConnectionState.ERROR)
        raise BackendConnectionException(
            f"Failed to connect to {self.config.host}:{self.config.port} after {self.config.max_retries} attempts"
        )
    
    def disconnect(self) -> None:
        """Disconnect from backend server."""
        self._running = False
        self._cleanup_socket()
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Disconnected from backend")
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._state == ConnectionState.CONNECTED
    
    def reconnect(self) -> bool:
        """Reconnect to backend."""
        self.disconnect()
        time.sleep(1)
        return self.connect()
    
    # ==================== Message Sending ====================
    
    def _send_frame(self, message_bytes: bytes) -> None:
        """Send frame via socket (internal)."""
        if not self._socket:
            raise BackendConnectionException("Not connected")
        
        frame = FrameCodec.encode(message_bytes)
        
        with self._socket_lock:
            try:
                self._socket.sendall(frame)
            except socket.timeout:
                raise BackendConnectionException("Socket send timeout")
            except Exception as e:
                self._cleanup_socket()
                raise BackendConnectionException(f"Socket send error: {e}")
    
    def _send_request(
        self,
        message_type: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send request and wait for response.
        
        Args:
            message_type: Type of message
            payload: Message payload
            timeout: Custom timeout (uses config default if None)
        
        Returns:
            Response payload
        
        Raises:
            BackendConnectionException: Connection error
            TimeoutError: Request timeout
            ValueError: Error response from server
        """
        if not self.is_connected():
            raise BackendConnectionException("Not connected to backend")
        
        # Create request
        request_id = str(uuid.uuid4())
        message = {
            "type": message_type,
            "requestId": request_id,
            "payload": payload
        }
        
        # Register pending request
        future = {
            "event": threading.Event(),
            "response": None,
            "error": None
        }
        
        with self._pending_lock:
            self._pending_requests[request_id] = future
        
        try:
            # Send message
            message_bytes = json.dumps(message).encode('utf-8')
            self._send_frame(message_bytes)
            
            logger.debug(f"Sent {message_type} request (ID: {request_id})")
            
            # Wait for response
            timeout_secs = timeout or self.config.timeout
            if not future["event"].wait(timeout=timeout_secs):
                raise TimeoutError(f"Request {request_id} timed out after {timeout_secs}s")
            
            # Check for error
            if future["error"]:
                raise future["error"]
            
            return future["response"]
        
        finally:
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)
    
    # ==================== Message Receiving ====================
    
    def _listen_loop(self) -> None:
        """Background listener thread (runs continuously)."""
        logger.info("Listener thread started")
        
        while self._running:
            try:
                data = self._socket.recv(4096)
                
                if not data:
                    logger.warning("Socket closed by server")
                    self._cleanup_socket()
                    break
                
                # Append to buffer
                self._frame_buffer.append(data)
                
                # Extract and process all complete frames
                while True:
                    frame = self._frame_buffer.extract_frame()
                    if frame is None:
                        break
                    
                    try:
                        message = json.loads(frame.decode('utf-8'))
                        self._process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
            
            except socket.timeout:
                pass  # Timeout is normal, continue
            
            except Exception as e:
                if self._running:
                    logger.error(f"Listener error: {e}", exc_info=True)
                    self._cleanup_socket()
                    break
        
        logger.info("Listener thread stopped")
    
    def _process_message(self, message: Dict[str, Any]) -> None:
        """Process received message."""
        message_type = message.get("type")
        request_id = message.get("requestId")
        payload = message.get("payload", {})
        
        # Handle response to pending request
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests[request_id]
            
            if message_type == "ERROR":
                error_code = payload.get("error", {}).get("code")
                error_msg = payload.get("error", {}).get("message")
                future["error"] = ValueError(f"{error_code}: {error_msg}")
            else:
                future["response"] = payload
            
            future["event"].set()
            logger.debug(f"Processed response for request {request_id}")
        
        # Handle unsolicited message (e.g., EVENT)
        elif message_type == "EVENT":
            # Backend broadcasts events with type=EVENT and
            # the real event type inside payload.eventType.
            # Extract it so callbacks registered with
            # on_event("NEW_FILE", cb) actually fire.
            event_type = (
                payload.get("event")
                or payload.get("eventType")
                or message_type
            )
            self._dispatch_event(event_type, payload)
        
        else:
            logger.debug(f"Received unsolicited message: {message_type}")
    
    def _dispatch_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Dispatch event to registered callbacks."""
        with self._callbacks_lock:
            callbacks = self._event_callbacks.get(event_type, [])
        
        for callback in callbacks:
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Error in event callback: {e}", exc_info=True)
    
    # ==================== Token Management ====================
    
    def set_token(self, token: str) -> None:
        """Store session token."""
        with self._token_lock:
            self._token = token
        logger.info("Token stored")
    
    def get_token(self) -> Optional[str]:
        """Get stored session token."""
        with self._token_lock:
            return self._token
    
    def clear_token(self) -> None:
        """Clear stored token."""
        with self._token_lock:
            self._token = None
        logger.info("Token cleared")
    
    def _add_token_to_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add token to payload if needed."""
        token = self.get_token()
        if token:
            payload = dict(payload)  # Copy
            payload["token"] = token
        return payload
    
    # ==================== Event Registration ====================
    
    def on_event(self, event_type: str, callback: Callable) -> None:
        """
        Register callback for event type.
        
        Args:
            event_type: Type of event (e.g., "NEW_FILE", "MEMBER_ADDED")
            callback: Function to call with event payload
        """
        with self._callbacks_lock:
            if event_type not in self._event_callbacks:
                self._event_callbacks[event_type] = []
            self._event_callbacks[event_type].append(callback)
        logger.info(f"Registered callback for {event_type}")
    
    def off_event(self, event_type: str, callback: Callable) -> None:
        """Unregister event callback."""
        with self._callbacks_lock:
            if event_type in self._event_callbacks:
                self._event_callbacks[event_type].remove(callback)
    
    # ==================== Helper Methods ====================
    
    def _set_state(self, state: ConnectionState) -> None:
        """Set connection state."""
        with self._state_lock:
            self._state = state
    
    def _cleanup_socket(self) -> None:
        """Clean up socket resources."""
        with self._socket_lock:
            if self._socket:
                try:
                    self._socket.close()
                except:
                    pass
                self._socket = None
        self._frame_buffer.clear()
    
    def __enter__(self):
        """Context manager enter."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    # ==================== API Methods ====================
    # Automatically adds token to payload for authenticated endpoints
    
    def signup(self, username: str, email: str, password: str) -> Dict[str, Any]:
        """
        Register new user.
        
        Returns:
            {userId, username, email}
        """
        response = self._send_request("SIGNUP", {
            "username": username,
            "email": email,
            "password": password
        })
        return response
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user.
        
        Returns:
            {token, expiresAt}
        """
        response = self._send_request("LOGIN", {
            "username": username,
            "password": password
        })
        # Store token
        self.set_token(response.get("token"))
        return response
    
    def logout(self) -> Dict[str, Any]:
        """Logout user."""
        response = self._send_request("LOGOUT", 
                                     self._add_token_to_payload({}))
        self.clear_token()
        return response
    
    def create_room(self, name: str) -> Dict[str, Any]:
        """Create room."""
        return self._send_request("CREATE_ROOM",
                                 self._add_token_to_payload({"name": name}))
    
    def list_rooms(self) -> Dict[str, Any]:
        """Get all rooms."""
        return self._send_request("LIST_ROOMS",
                                 self._add_token_to_payload({}))
    
    def list_members(self, room_id: str) -> Dict[str, Any]:
        """Get room members."""
        return self._send_request("LIST_MEMBERS",
                                 self._add_token_to_payload({"roomId": room_id}))
    
    def add_member(self, room_id: str, user_id: str, role: str) -> Dict[str, Any]:
        """Add member to room."""
        return self._send_request("ADD_MEMBER",
                                 self._add_token_to_payload({
                                     "roomId": room_id,
                                     "userId": user_id,
                                     "role": role
                                 }))
    
    def remove_member(self, room_id: str, user_id: str) -> Dict[str, Any]:
        """Remove member from room."""
        return self._send_request("REMOVE_MEMBER",
                                 self._add_token_to_payload({
                                     "roomId": room_id,
                                     "userId": user_id
                                 }))
    
    def set_role(self, room_id: str, user_id: str, new_role: str) -> Dict[str, Any]:
        """Change member role."""
        return self._send_request("SET_ROLE",
                                 self._add_token_to_payload({
                                     "roomId": room_id,
                                     "userId": user_id,
                                     "newRole": new_role
                                 }))
    
    def list_files(self, room_id: str) -> Dict[str, Any]:
        """Get files in room."""
        response = self._send_request("LIST_FILES",
                                     self._add_token_to_payload({"roomId": room_id}))
        return response.get("files", [])
    
    def file_detail(self, file_id: str) -> Dict[str, Any]:
        """Get file details."""
        return self._send_request("FILE_DETAIL",
                                 self._add_token_to_payload({"fileId": file_id}))
    
    # NOTE: file_versions is intentionally replaced by the protocol-correct
    # version below. The old signature accepted fileId but the backend
    # protocol requires roomId + originalName.
    def file_versions(self, room_id: str, original_name: str) -> Dict[str, Any]:
        """
        Get file versions (by room and original name).
        
        Backend protocol: FILE_VERSIONS expects {roomId, originalName}.
        
        Args:
            room_id: Room containing the file
            original_name: Original filename (not fileId)
        
        Returns:
            {versions: [...]}
        """
        response = self._send_request("FILE_VERSIONS",
                                     self._add_token_to_payload({
                                         "roomId": room_id,
                                         "originalName": original_name
                                     }))
        return response.get("versions", [])
    
    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete file."""
        return self._send_request("DELETE_FILE",
                                 self._add_token_to_payload({"fileId": file_id}))
    
    def init_upload(
        self,
        room_id: str,
        file_info: Dict[str, Any],
        storage_address: str = "localhost:9000"
    ) -> Dict[str, Any]:
        """
        Initialize file upload.

        Backend protocol expects file_info with:
          - originalName (str)  -- was: name
          - sizeBytes (int)     -- was: size
          - mimeType (str)      -- was: missing
          - sha256Whole (str)   -- unchanged

        This method normalizes field names so existing callers can still
        pass convenience names (name, size) and they get translated to
        the backend's expected names.  chunkCount/chunkSize are no longer
        sent to the control plane (they are data-plane properties derived
        by the storage node).

        Args:
            room_id: Target room
            file_info: dict with file metadata (convenience names accepted)
            storage_address: Optional storage node address

        Returns:
            {fileId, ticket, storageAddress, storageNodeId, chunkSize,
             totalChunks, deduplicated, ...}
        """
        # Normalize file_info to backend protocol field names.
        # Allows existing callers to use convenience names (name, size)
        # while ensuring the wire format matches backend expectations.
        normalized_file_info = {}
        normalized_file_info["originalName"] = file_info.get(
            "originalName", file_info.get("name", "unknown")
        )
        normalized_file_info["sizeBytes"] = file_info.get(
            "sizeBytes", file_info.get("size", 0)
        )
        normalized_file_info["mimeType"] = file_info.get(
            "mimeType", file_info.get("mime_type", "application/octet-stream")
        )
        normalized_file_info["sha256Whole"] = file_info.get(
            "sha256Whole", file_info.get("sha256_whole", "")
        )

        return self._send_request("INIT_UPLOAD",
                                 self._add_token_to_payload({
                                     "roomId": room_id,
                                     "fileInfo": normalized_file_info,
                                     "storageAddress": storage_address
                                 }))
    
    def init_download(
        self,
        file_id: str,
        version: int = None,
        share_token: str = None
    ) -> Dict[str, Any]:
        """
        Initialize file download.
        
        Args:
            file_id: File to download
            version: Optional version number
            share_token: Optional public share token (no auth required)
        
        Returns:
            {downloadId, storageNodeId, ticket, fileInfo, ...}
        """
        payload = {}
        if share_token:
            payload["shareToken"] = share_token
        else:
            payload = self._add_token_to_payload({})
        
        payload["fileId"] = file_id
        if version:
            payload["version"] = version
        
        return self._send_request("INIT_DOWNLOAD", payload)
    
    def create_share_token(
        self,
        file_id: str,
        expiry_seconds: int = 86400,
        max_downloads: int = 0
    ) -> Dict[str, Any]:
        """
        Create public share link.

        Backend protocol requires:
          - maxDownloads (int, 0 = unlimited)
          - expiresAt (ISO 8601 datetime string)

        This method converts the convenience expiry_seconds parameter
        into the backend's expected format.

        The backend returns "token" in the response; the service layer
        normalises this to "shareToken" for backward compatibility.

        Args:
            file_id: File to share
            expiry_seconds: Link expiration in seconds from now
            max_downloads: Max number of downloads (0 = unlimited)

        Returns:
            {token, fileId, maxDownloads, expiresAt}
        """
        from datetime import datetime, timezone, timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)).isoformat()

        return self._send_request("CREATE_SHARE_TOKEN",
                                 self._add_token_to_payload({
                                     "fileId": file_id,
                                     "maxDownloads": max_downloads,
                                     "expiresAt": expires_at
                                 }))
    
    def subscribe_room(self, room_id: str) -> Dict[str, Any]:
        """
        Subscribe to room events.
        
        Returns:
            {success, roomId}
        """
        return self._send_request("SUBSCRIBE_ROOM",
                                 self._add_token_to_payload({"roomId": room_id}))
    
    def unsubscribe_room(self, room_id: str) -> Dict[str, Any]:
        """Unsubscribe from room events."""
        return self._send_request(
            "UNSUBSCRIBE_ROOM",
            self._add_token_to_payload({"roomId": room_id})
        )
        
    def ping(self) -> Dict[str, Any]:
        """Health check."""
        return self._send_request("PING", {})
    
    def status(self) -> Dict[str, Any]:
        """Get server status."""
        return self._send_request("STATUS", {})


# Example usage
if __name__ == "__main__":
    # Create client with custom config
    config = BackendConfig(host="localhost", port=8080, timeout=10)
    client = BackendClient(config)
    
    try:
        # Connect
        client.connect()
        print("Connected!")
        
        # Signup
        result = client.signup("testuser", "test@example.com", "password123")
        print(f"Signup: {result}")
        
        # Login
        result = client.login("testuser", "password123")
        print(f"Login: {result}")
        
        # List rooms
        rooms = client.list_rooms()
        print(f"Rooms: {rooms}")
        
        # Subscribe to room events
        if rooms.get("rooms"):
            room_id = rooms["rooms"][0]["roomId"]
            client.subscribe_room(room_id)
            
            # Register event handler
            def on_new_file(payload):
                print(f"New file: {payload}")
            
            client.on_event("NEW_FILE", on_new_file)
            
            # Keep listening for 10 seconds
            time.sleep(10)
    
    finally:
        client.disconnect()