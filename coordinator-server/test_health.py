"""Unit tests for health check functionality."""
import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
from health.health_service import HealthService
from health.health_handlers import HealthHandlers
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.socket_server import SocketConnection


class TestHealthService:
    """Test HealthService class."""
    
    def test_ping_returns_pong_and_timestamp(self):
        """Test that ping returns pong and current timestamp."""
        # Setup
        db = Mock()
        redis_client = Mock()
        service = HealthService(db, redis_client)
        
        # Execute
        result = service.ping()
        
        # Verify
        assert result['pong'] is True
        assert 'timestamp' in result
        # Verify timestamp is ISO format
        datetime.fromisoformat(result['timestamp'].replace('Z', '+00:00'))
    
    def test_get_status_returns_uptime(self):
        """Test that get_status returns uptime."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        service = HealthService(db, redis_client)
        
        # Wait a bit to ensure uptime > 0
        time.sleep(0.1)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert 'uptime' in result
        assert result['uptime'] >= 0
        assert isinstance(result['uptime'], int)
    
    def test_get_status_checks_postgres(self):
        """Test that get_status checks PostgreSQL connection."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        service = HealthService(db, redis_client)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert 'postgres' in result
        assert result['postgres']['status'] == 'connected'
        assert result['postgres']['healthy'] is True
        db.execute_query.assert_called_once_with("SELECT 1 as test")
    
    def test_get_status_checks_redis(self):
        """Test that get_status checks Redis connection."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        service = HealthService(db, redis_client)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert 'redis' in result
        assert result['redis']['status'] == 'connected'
        assert result['redis']['healthy'] is True
        redis_client.ping.assert_called_once()
    
    def test_get_status_handles_postgres_failure(self):
        """Test that get_status handles PostgreSQL connection failure."""
        # Setup
        db = Mock()
        db.execute_query.side_effect = Exception("Connection failed")
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        service = HealthService(db, redis_client)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert result['postgres']['status'] == 'error'
        assert result['postgres']['healthy'] is False
        assert 'error' in result['postgres']
    
    def test_get_status_handles_redis_failure(self):
        """Test that get_status handles Redis connection failure."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.side_effect = Exception("Connection failed")
        
        service = HealthService(db, redis_client)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert result['redis']['status'] == 'error'
        assert result['redis']['healthy'] is False
        assert 'error' in result['redis']
    
    def test_get_status_checks_storage_nodes(self):
        """Test that get_status checks Storage Node connections."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        storage_node_server = Mock()
        storage_node_server.get_connected_nodes.return_value = [
            {'node_id': 'node1', 'healthy': True},
            {'node_id': 'node2', 'healthy': True}
        ]
        
        service = HealthService(db, redis_client, storage_node_server)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert 'storageNodes' in result
        assert result['storageNodes']['status'] == 'connected'
        assert result['storageNodes']['healthy'] is True
        assert result['storageNodes']['connectedNodes'] == 2
        assert result['storageNodes']['healthyNodes'] == 2
    
    def test_get_status_handles_no_storage_nodes(self):
        """Test that get_status handles no Storage Node server configured."""
        # Setup
        db = Mock()
        db.execute_query.return_value = [{'test': 1}]
        redis_client = Mock()
        redis_client.ping.return_value = True
        
        service = HealthService(db, redis_client, storage_node_server=None)
        
        # Execute
        result = service.get_status()
        
        # Verify
        assert result['storageNodes']['status'] == 'not_configured'
        assert result['storageNodes']['healthy'] is False
        assert result['storageNodes']['connectedNodes'] == 0


class TestHealthHandlers:
    """Test HealthHandlers class."""
    
    def test_handle_ping_sends_pong(self):
        """Test that handle_ping sends PONG response."""
        # Setup
        health_service = Mock()
        health_service.ping.return_value = {
            'pong': True,
            'timestamp': '2024-01-01T00:00:00+00:00'
        }
        
        handlers = HealthHandlers(health_service)
        
        connection = Mock(spec=SocketConnection)
        connection.connection_id = "test-connection"
        
        message = Message(
            type=MessageType.PING,
            payload={},
            request_id="test-request-id"
        )
        
        # Execute
        handlers.handle_ping(connection, message)
        
        # Verify
        health_service.ping.assert_called_once()
        connection.send_message.assert_called_once()
        
        sent_message = connection.send_message.call_args[0][0]
        assert sent_message.type == MessageType.PONG
        assert sent_message.payload['pong'] is True
        assert 'timestamp' in sent_message.payload
        assert sent_message.request_id == "test-request-id"
    
    def test_handle_status_sends_status_response(self):
        """Test that handle_status sends STATUS_RESPONSE."""
        # Setup
        health_service = Mock()
        health_service.get_status.return_value = {
            'uptime': 100,
            'postgres': {'status': 'connected', 'healthy': True},
            'redis': {'status': 'connected', 'healthy': True},
            'storageNodes': {'status': 'connected', 'healthy': True, 'connectedNodes': 1},
            'timestamp': '2024-01-01T00:00:00+00:00'
        }
        
        handlers = HealthHandlers(health_service)
        
        connection = Mock(spec=SocketConnection)
        connection.connection_id = "test-connection"
        
        message = Message(
            type=MessageType.STATUS,
            payload={},
            request_id="test-request-id"
        )
        
        # Execute
        handlers.handle_status(connection, message)
        
        # Verify
        health_service.get_status.assert_called_once()
        connection.send_message.assert_called_once()
        
        sent_message = connection.send_message.call_args[0][0]
        assert sent_message.type == MessageType.STATUS_RESPONSE
        assert sent_message.payload['uptime'] == 100
        assert 'postgres' in sent_message.payload
        assert 'redis' in sent_message.payload
        assert 'storageNodes' in sent_message.payload
        assert sent_message.request_id == "test-request-id"
    
    def test_handle_status_sends_error_on_exception(self):
        """Test that handle_status sends error response on exception."""
        # Setup
        health_service = Mock()
        health_service.get_status.side_effect = Exception("Internal error")
        
        handlers = HealthHandlers(health_service)
        
        connection = Mock(spec=SocketConnection)
        connection.connection_id = "test-connection"
        
        message = Message(
            type=MessageType.STATUS,
            payload={},
            request_id="test-request-id"
        )
        
        # Execute
        handlers.handle_status(connection, message)
        
        # Verify
        connection.send_message.assert_called_once()
        
        sent_message = connection.send_message.call_args[0][0]
        assert sent_message.type == MessageType.ERROR
        assert sent_message.get_error_code() == "INTERNAL_ERROR"
        assert sent_message.request_id == "test-request-id"
    
    def test_ping_does_not_require_authentication(self):
        """Test that PING handler does not check authentication."""
        # Setup
        health_service = Mock()
        health_service.ping.return_value = {
            'pong': True,
            'timestamp': '2024-01-01T00:00:00+00:00'
        }
        
        handlers = HealthHandlers(health_service)
        
        connection = Mock(spec=SocketConnection)
        connection.connection_id = "unauthenticated-connection"
        
        message = Message(
            type=MessageType.PING,
            payload={},  # No token
            request_id="test-request-id"
        )
        
        # Execute - should not raise any authentication error
        handlers.handle_ping(connection, message)
        
        # Verify - response sent successfully
        connection.send_message.assert_called_once()
        sent_message = connection.send_message.call_args[0][0]
        assert sent_message.type == MessageType.PONG
