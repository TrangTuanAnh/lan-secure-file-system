"""Integration tests for health check functionality."""
import pytest
import socket
import json
import struct
from unittest.mock import Mock
from health.health_service import HealthService
from health.health_handlers import HealthHandlers
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.frame_codec import FrameCodec


class TestHealthCheckIntegration:
    """Integration tests for health check handlers with socket server."""
    
    def test_ping_handler_integration(self):
        """Test PING handler integration with socket connection."""
        # Setup
        db = Mock()
        redis_client = Mock()
        health_service = HealthService(db, redis_client)
        health_handlers = HealthHandlers(health_service)
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create PING message
        ping_message = Message.create_request(MessageType.PING, {})
        
        # Execute handler
        health_handlers.handle_ping(connection, ping_message)
        
        # Verify send_message was called
        assert mock_socket.sendall.called
        
        # Extract sent data
        sent_data = mock_socket.sendall.call_args[0][0]
        
        # Decode frame
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        
        # Parse message
        response = Message.from_bytes(message_bytes)
        
        # Verify response
        assert response.type == MessageType.PONG
        assert response.payload['pong'] is True
        assert 'timestamp' in response.payload
        assert response.request_id == ping_message.request_id
    
    def test_status_handler_integration(self):
        """Test STATUS handler integration with socket connection."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        health_service = HealthService(db, redis_client)
        health_handlers = HealthHandlers(health_service)
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create STATUS message
        status_message = Message.create_request(MessageType.STATUS, {})
        
        # Execute handler
        health_handlers.handle_status(connection, status_message)
        
        # Verify send_message was called
        assert mock_socket.sendall.called
        
        # Extract sent data
        sent_data = mock_socket.sendall.call_args[0][0]
        
        # Decode frame
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        
        # Parse message
        response = Message.from_bytes(message_bytes)
        
        # Verify response
        assert response.type == MessageType.STATUS_RESPONSE
        assert 'uptime' in response.payload
        assert 'postgres' in response.payload
        assert 'redis' in response.payload
        assert 'storageNodes' in response.payload
        assert 'timestamp' in response.payload
        assert response.request_id == status_message.request_id
    
    def test_ping_works_without_authentication(self):
        """Test that PING works without any authentication token."""
        # Setup
        db = Mock()
        redis_client = Mock()
        health_service = HealthService(db, redis_client)
        health_handlers = HealthHandlers(health_service)
        
        # Create mock connection (no authentication)
        mock_socket = Mock(spec=socket.socket)
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create PING message without any token
        ping_message = Message(
            type=MessageType.PING,
            payload={},  # No token field
            request_id="test-request"
        )
        
        # Execute handler - should not raise any error
        health_handlers.handle_ping(connection, ping_message)
        
        # Verify response was sent
        assert mock_socket.sendall.called
        
        # Extract and verify response
        sent_data = mock_socket.sendall.call_args[0][0]
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        response = Message.from_bytes(message_bytes)
        
        # Should be PONG, not ERROR
        assert response.type == MessageType.PONG
        assert response.payload['pong'] is True
