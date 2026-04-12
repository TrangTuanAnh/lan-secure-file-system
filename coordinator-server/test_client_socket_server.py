"""Integration tests for client socket server."""
import pytest
import socket
import struct
from unittest.mock import Mock, MagicMock
from client_socket_server import ClientSocketServer
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.frame_codec import FrameCodec


class TestClientSocketServer:
    """Integration tests for ClientSocketServer."""
    
    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing."""
        return {
            'auth_service': Mock(),
            'authorization_service': Mock(),
            'room_service': Mock(),
            'file_service': Mock(),
            'upload_service': Mock(),
            'download_service': Mock(),
            'notification_service': Mock(),
            'health_service': Mock()
        }
    
    def test_server_initialization(self, mock_services):
        """Test that server initializes correctly."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,  # Use port 0 to let OS assign a free port
            **mock_services
        )
        
        assert server.host == '127.0.0.1'
        assert server.port == 0
        assert server.name == "ClientSocketServer"
        assert server.auth_service == mock_services['auth_service']
        assert server.notification_service == mock_services['notification_service']
    
    def test_ping_handler_registered(self, mock_services):
        """Test that PING handler is registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify PING handler is registered
        assert MessageType.PING in server._handlers
    
    def test_authentication_handlers_registered(self, mock_services):
        """Test that authentication handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify authentication handlers are registered
        assert MessageType.SIGNUP in server._handlers
        assert MessageType.LOGIN in server._handlers
        assert MessageType.LOGOUT in server._handlers
    
    def test_room_handlers_registered(self, mock_services):
        """Test that room management handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify room handlers are registered
        assert MessageType.CREATE_ROOM in server._handlers
        assert MessageType.ADD_MEMBER in server._handlers
        assert MessageType.REMOVE_MEMBER in server._handlers
        assert MessageType.SET_ROLE in server._handlers
        assert MessageType.LIST_ROOMS in server._handlers
        assert MessageType.LIST_MEMBERS in server._handlers
    
    def test_file_handlers_registered(self, mock_services):
        """Test that file operation handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify file handlers are registered
        assert MessageType.LIST_FILES in server._handlers
        assert MessageType.FILE_DETAIL in server._handlers
        assert MessageType.FILE_VERSIONS in server._handlers
        assert MessageType.DELETE_FILE in server._handlers
    
    def test_upload_download_handlers_registered(self, mock_services):
        """Test that upload/download handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify upload/download handlers are registered
        assert MessageType.INIT_UPLOAD in server._handlers
        assert MessageType.INIT_DOWNLOAD in server._handlers
        assert MessageType.CREATE_SHARE_TOKEN in server._handlers
    
    def test_notification_handlers_registered(self, mock_services):
        """Test that notification handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify notification handlers are registered
        assert MessageType.SUBSCRIBE_ROOM in server._handlers
        assert MessageType.UNSUBSCRIBE_ROOM in server._handlers
    
    def test_health_handlers_registered(self, mock_services):
        """Test that health check handlers are registered."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Verify health handlers are registered
        assert MessageType.PING in server._handlers
        assert MessageType.STATUS in server._handlers
    
    def test_ping_handler_no_auth_required(self, mock_services):
        """Test that PING handler works without authentication."""
        # Setup mock health service
        mock_services['health_service'].ping.return_value = {
            'pong': True,
            'timestamp': 1234567890
        }
        
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        from protocol.socket_server import SocketConnection
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create PING message (no token)
        ping_message = Message.create_request(MessageType.PING, {})
        
        # Get handler and execute
        handler = server._handlers[MessageType.PING]
        handler(connection, ping_message)
        
        # Verify response was sent
        assert mock_socket.sendall.called
        
        # Extract and verify response
        sent_data = mock_socket.sendall.call_args[0][0]
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        response = Message.from_bytes(message_bytes)
        
        # Should be PONG, not ERROR
        assert response.type == MessageType.PONG
    
    def test_authenticated_request_requires_token(self, mock_services):
        """Test that authenticated requests require a valid token."""
        # Setup mock auth service to reject invalid token
        mock_services['auth_service'].validate_token.return_value = (
            False,
            None,
            "INVALID_TOKEN"
        )
        
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        from protocol.socket_server import SocketConnection
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create LIST_ROOMS message without token
        list_rooms_message = Message.create_request(
            MessageType.LIST_ROOMS,
            {}  # No token
        )
        
        # Get handler and execute
        handler = server._handlers[MessageType.LIST_ROOMS]
        handler(connection, list_rooms_message)
        
        # Verify response was sent
        assert mock_socket.sendall.called
        
        # Extract and verify response
        sent_data = mock_socket.sendall.call_args[0][0]
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        response = Message.from_bytes(message_bytes)
        
        # Should be ERROR
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "AUTH_REQUIRED"
    
    def test_connection_cleanup_on_close(self, mock_services):
        """Test that notification subscriptions are cleaned up when connection closes."""
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        from protocol.socket_server import SocketConnection
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Call connection closed callback
        server._on_connection_closed(connection)
        
        # Verify notification service cleanup was called
        mock_services['notification_service'].remove_connection.assert_called_once_with(connection)
    
    def test_init_download_with_share_token(self, mock_services):
        """Test INIT_DOWNLOAD with share token (no auth required)."""
        # Setup mock download service (not handlers)
        mock_services['download_service'].handle_init_download_share = Mock(
            return_value=(
                True,  # success
                {  # download_plan
                    'ticket': 'test-ticket',
                    'storageAddress': 'localhost:9000'
                },
                None  # error_code
            )
        )
        
        server = ClientSocketServer(
            host='127.0.0.1',
            port=0,
            **mock_services
        )
        
        # Create mock connection
        mock_socket = Mock(spec=socket.socket)
        from protocol.socket_server import SocketConnection
        connection = SocketConnection(mock_socket, ("127.0.0.1", 12345))
        
        # Create INIT_DOWNLOAD message with share token
        download_message = Message.create_request(
            MessageType.INIT_DOWNLOAD,
            {
                'shareToken': 'test-share-token',
                'fileId': 'test-file-id'
            }
        )
        
        # Get handler and execute
        handler = server._handlers[MessageType.INIT_DOWNLOAD]
        handler(connection, download_message)
        
        # Verify download service was called with share token
        mock_services['download_service'].handle_init_download_share.assert_called_once()
        
        # Verify response was sent
        assert mock_socket.sendall.called
        
        # Extract and verify response
        sent_data = mock_socket.sendall.call_args[0][0]
        length = struct.unpack('>I', sent_data[:4])[0]
        message_bytes = sent_data[4:4+length]
        response = Message.from_bytes(message_bytes)
        
        # Should be DOWNLOAD_PLAN
        assert response.type == MessageType.DOWNLOAD_PLAN
        assert response.payload['ticket'] == 'test-ticket'
