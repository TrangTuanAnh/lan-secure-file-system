"""Tests for Storage Node communication module."""
import pytest
import socket
import time
import json
import uuid
from datetime import datetime, timezone, timedelta
from storage_node.storage_node_server import StorageNodeServer, StorageNodeInfo
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.frame_codec import FrameCodec
from ticket.ticket_service import TicketService
from upload.upload_service import UploadService


class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.users = []
        self.rooms = []
        self.files = []
        self.room_members = []
    
    def execute_query(self, query: str, params: tuple = None):
        """Mock query execution."""
        if "SELECT status FROM files WHERE id" in query:
            file_id = params[0]
            return [{'status': f['status']} for f in self.files if f['id'] == file_id]
        if "FROM files" in query and "WHERE id" in query:
            file_id = params[0]
            files = [f for f in self.files if f['id'] == file_id]
            return files
        return []
    
    def execute_update(self, query: str, params: tuple = None):
        """Mock update execution."""
        if "UPDATE files SET status" in query:
            status, file_id = params
            for f in self.files:
                if f['id'] == file_id:
                    f['status'] = status
            return 1
        return 0
    
    def close(self):
        """Mock close."""
        pass


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.tickets = {}
    
    def set_ticket(self, ticket_id: str, data: dict, ttl: int):
        """Store ticket."""
        self.tickets[ticket_id] = data
    
    def get_ticket(self, ticket_id: str):
        """Retrieve ticket."""
        return self.tickets.get(ticket_id)
    
    def delete_ticket(self, ticket_id: str):
        """Delete ticket."""
        return self.tickets.pop(ticket_id, None) is not None
    
    def close(self):
        """Mock close."""
        pass


class MockAuthorizationService:
    """Mock authorization service."""
    
    def __init__(self):
        pass
    
    def check_permission(self, user_id, global_role, room_id, action):
        """Mock permission check."""
        return True


class MockAuditService:
    """Mock audit service."""
    
    def __init__(self):
        self.logs = []
    
    def write_audit_log(self, actor_id, action, target_type, target_id, room_id, detail, status):
        """Mock audit log write."""
        self.logs.append({
            'actor_id': actor_id,
            'action': action,
            'target_type': target_type,
            'target_id': target_id,
            'room_id': room_id,
            'detail': detail,
            'status': status
        })


class MockConnection:
    """Mock socket connection for testing."""
    
    def __init__(self):
        self.connection_id = "test-connection"
        self.sent_messages = []
    
    def send_message(self, message: Message):
        """Record sent message."""
        self.sent_messages.append(message)


def send_message_to_server(sock: socket.socket, message: Message) -> None:
    """
    Send a message to the server.
    
    Args:
        sock: Socket connection
        message: Message to send
    """
    message_bytes = message.to_bytes()
    frame = FrameCodec.encode(message_bytes)
    sock.sendall(frame)


def receive_message_from_server(sock: socket.socket) -> Message:
    """
    Receive a message from the server.
    
    Args:
        sock: Socket connection
    
    Returns:
        Received message
    """
    # Read length prefix (4 bytes)
    length_bytes = b''
    while len(length_bytes) < 4:
        chunk = sock.recv(4 - len(length_bytes))
        if not chunk:
            raise ConnectionError("Connection closed")
        length_bytes += chunk
    
    # Parse length
    length = int.from_bytes(length_bytes, byteorder='big')
    
    # Read message
    message_bytes = b''
    while len(message_bytes) < length:
        chunk = sock.recv(length - len(message_bytes))
        if not chunk:
            raise ConnectionError("Connection closed")
        message_bytes += chunk
    
    return Message.from_bytes(message_bytes)


@pytest.fixture
def test_db():
    """Create test database."""
    return MockDatabase()


@pytest.fixture
def test_redis():
    """Create test Redis client."""
    return MockRedisClient()


@pytest.fixture
def ticket_service(test_redis):
    """Create ticket service."""
    return TicketService(
        redis_client=test_redis,
        upload_ticket_ttl_seconds=1800,
        download_ticket_ttl_seconds=900
    )


@pytest.fixture
def upload_service(test_db, test_redis):
    """Create upload service."""
    authz = MockAuthorizationService()
    audit = MockAuditService()
    
    return UploadService(
        database=test_db,
        redis_client=test_redis,
        authorization_service=authz,
        audit_service=audit,
        notification_service=None,
        chunk_size=524288,
        ticket_ttl_seconds=1800
    )


@pytest.fixture
def storage_server(test_db, ticket_service, upload_service):
    """Create and start Storage Node server."""
    server = StorageNodeServer(
        host='127.0.0.1',
        port=18081,  # Use different port for testing
        shared_secret='test-secret',
        ticket_service=ticket_service,
        upload_service=upload_service,
        timeout_seconds=90
    )
    server.start()
    time.sleep(0.5)  # Give server time to start
    yield server
    server.stop()


def test_storage_node_info():
    """Test StorageNodeInfo class."""
    mock_conn = MockConnection()
    node_info = StorageNodeInfo(mock_conn, "test-node-1")
    
    assert node_info.node_id == "test-node-1"
    assert not node_info.authenticated
    assert not node_info.is_healthy(90)
    node_info.authenticated = True
    assert node_info.is_healthy(90)
    
    # Test ping update
    initial_time = node_info.last_ping_time
    time.sleep(0.1)
    node_info.update_ping_time()
    assert node_info.last_ping_time > initial_time
    
    # Test health check timeout
    node_info.last_ping_time = time.time() - 100
    assert not node_info.is_healthy(90)


def test_storage_auth_success(storage_server):
    """Test successful Storage Node authentication."""
    # Connect to server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Send STORAGE_AUTH with correct secret
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        
        # Receive response
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.STORAGE_AUTH_RESPONSE
        assert response.payload['status'] == 'authenticated'
        assert response.request_id == auth_msg.request_id
    
    finally:
        sock.close()


def test_storage_auth_records_advertised_address(storage_server):
    """Test Storage Node auth records node id and data-plane address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))

    try:
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {
                "secret": "test-secret",
                "nodeId": "storage-node-1",
                "dataHost": "storage-node-1",
                "dataPort": 9001,
                "storageAddress": "storage-node-1:9001"
            }
        )
        send_message_to_server(sock, auth_msg)
        response = receive_message_from_server(sock)

        assert response.type == MessageType.STORAGE_AUTH_RESPONSE
        assert response.payload['nodeId'] == 'storage-node-1'

        nodes = storage_server.get_connected_nodes()
        assert len(nodes) == 1
        assert nodes[0]['nodeId'] == 'storage-node-1'
        assert nodes[0]['storageAddress'] == 'storage-node-1:9001'
        assert nodes[0]['dataPort'] == 9001

    finally:
        sock.close()


def test_storage_auth_invalid_secret(storage_server):
    """Test Storage Node authentication with invalid secret."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Send STORAGE_AUTH with wrong secret
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "wrong-secret"}
        )
        send_message_to_server(sock, auth_msg)
        
        # Receive error response
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "INVALID_SECRET"
    
    finally:
        sock.close()


def test_storage_auth_missing_secret(storage_server):
    """Test Storage Node authentication with missing secret."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Send STORAGE_AUTH without secret
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {}
        )
        send_message_to_server(sock, auth_msg)
        
        # Receive error response
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "MISSING_SECRET"
    
    finally:
        sock.close()


def test_ping_pong(storage_server):
    """Test PING/PONG heartbeat."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate first
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)  # Consume auth response
        
        # Send PING
        ping_msg = Message.create_request(MessageType.PING, {})
        send_message_to_server(sock, ping_msg)
        
        # Receive PONG
        pong = receive_message_from_server(sock)
        
        assert pong.type == MessageType.PONG
        assert 'timestamp' in pong.payload
        assert pong.request_id == ping_msg.request_id
    
    finally:
        sock.close()


def test_ping_without_auth(storage_server):
    """Test PING without authentication."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Send PING without authenticating
        ping_msg = Message.create_request(MessageType.PING, {})
        send_message_to_server(sock, ping_msg)
        
        # Receive error
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "NOT_AUTHENTICATED"
    
    finally:
        sock.close()


def test_verify_ticket_valid(storage_server, ticket_service):
    """Test VERIFY_TICKET with valid ticket."""
    # Create a ticket
    ticket_id = ticket_service.generate_upload_ticket(
        file_id='file-123',
        user_id='user-456',
        room_id='room-789',
        total_chunks=10,
        chunk_size=524288,
        sha256_whole='a' * 64,
        stored_name='room-789/file-123'
    )
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send VERIFY_TICKET
        verify_msg = Message.create_request(
            MessageType.VERIFY_TICKET,
            {"ticket": ticket_id}
        )
        send_message_to_server(sock, verify_msg)
        
        # Receive TICKET_VALID
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.TICKET_VALID
        assert response.payload['fileId'] == 'file-123'
        assert response.payload['type'] == 'upload'
        assert response.payload['totalChunks'] == 10
    
    finally:
        sock.close()


def test_verify_ticket_invalid(storage_server):
    """Test VERIFY_TICKET with invalid ticket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send VERIFY_TICKET with non-existent ticket
        verify_msg = Message.create_request(
            MessageType.VERIFY_TICKET,
            {"ticket": "invalid-ticket-id"}
        )
        send_message_to_server(sock, verify_msg)
        
        # Receive TICKET_INVALID
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.TICKET_INVALID
        assert response.payload['error'] == 'TICKET_NOT_FOUND'
    
    finally:
        sock.close()


def test_upload_complete_message_handling(storage_server):
    """Test UPLOAD_COMPLETE message is received and processed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send UPLOAD_COMPLETE (will fail because file doesn't exist, but that's OK)
        complete_msg = Message.create_request(
            MessageType.UPLOAD_COMPLETE,
            {
                "fileId": str(uuid.uuid4()),
                "sha256Whole": 'a' * 64,
                "storedName": 'room/file',
                "finalSize": 1024
            }
        )
        send_message_to_server(sock, complete_msg)
        
        # Receive response (will be ERROR because file doesn't exist)
        response = receive_message_from_server(sock)
        
        # The server should respond (either ACK or ERROR)
        assert response.type in [MessageType.ACK, MessageType.ERROR]
        assert response.request_id == complete_msg.request_id
    
    finally:
        sock.close()


def test_upload_complete_missing_fields(storage_server):
    """Test UPLOAD_COMPLETE with missing required fields."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send UPLOAD_COMPLETE with missing fields
        complete_msg = Message.create_request(
            MessageType.UPLOAD_COMPLETE,
            {
                "fileId": str(uuid.uuid4())
                # Missing sha256Whole, storedName, finalSize
            }
        )
        send_message_to_server(sock, complete_msg)
        
        # Receive error
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "INVALID_PAYLOAD"
    
    finally:
        sock.close()


def test_upload_failed_message_handling(storage_server):
    """Test UPLOAD_FAILED message is received and processed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send UPLOAD_FAILED (will fail because file doesn't exist, but that's OK)
        failed_msg = Message.create_request(
            MessageType.UPLOAD_FAILED,
            {
                "fileId": str(uuid.uuid4()),
                "reason": "Disk full"
            }
        )
        send_message_to_server(sock, failed_msg)
        
        # Receive response (will be ERROR because file doesn't exist)
        response = receive_message_from_server(sock)
        
        # The server should respond (either ACK or ERROR)
        assert response.type in [MessageType.ACK, MessageType.ERROR]
        assert response.request_id == failed_msg.request_id
    
    finally:
        sock.close()


def test_upload_failed_missing_file_id(storage_server):
    """Test UPLOAD_FAILED with missing fileId."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        # Authenticate
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Send UPLOAD_FAILED without fileId
        failed_msg = Message.create_request(
            MessageType.UPLOAD_FAILED,
            {
                "reason": "Disk full"
            }
        )
        send_message_to_server(sock, failed_msg)
        
        # Receive error
        response = receive_message_from_server(sock)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "INVALID_PAYLOAD"
    
    finally:
        sock.close()


def test_get_connected_nodes(storage_server):
    """Test getting list of connected nodes."""
    # Initially no nodes
    nodes = storage_server.get_connected_nodes()
    assert len(nodes) == 0
    
    # Connect and authenticate
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 18081))
    
    try:
        auth_msg = Message.create_request(
            MessageType.STORAGE_AUTH,
            {"secret": "test-secret"}
        )
        send_message_to_server(sock, auth_msg)
        receive_message_from_server(sock)
        
        # Check connected nodes
        time.sleep(0.1)
        nodes = storage_server.get_connected_nodes()
        assert len(nodes) == 1
        assert nodes[0]['authenticated'] is True
        assert nodes[0]['healthy'] is True
    
    finally:
        sock.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
