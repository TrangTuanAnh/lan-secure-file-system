"""Tests for ticket verification handlers."""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
from protocol.message import Message
from protocol.message_types import MessageType
from ticket.ticket_handlers import TicketHandlers


class TestTicketHandlers:
    """Test suite for TicketHandlers."""
    
    @pytest.fixture
    def mock_ticket_service(self):
        """Create mock ticket service."""
        service = Mock()
        service.verify_ticket = Mock()
        return service
    
    @pytest.fixture
    def ticket_handlers(self, mock_ticket_service):
        """Create TicketHandlers instance with mock service."""
        return TicketHandlers(ticket_service=mock_ticket_service)
    
    def test_handle_verify_ticket_valid_upload(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with valid upload ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        ticket_metadata = {
            'type': 'upload',
            'fileId': str(uuid.uuid4()),
            'userId': str(uuid.uuid4()),
            'roomId': str(uuid.uuid4()),
            'totalChunks': 10,
            'chunkSize': 524288,
            'sha256Whole': 'a' * 64,
            'storedName': 'room/file',
            'expiresAt': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        }
        
        mock_ticket_service.verify_ticket.return_value = (True, ticket_metadata, None)
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.TICKET_VALID
        assert response.request_id == request_id
        assert response.payload['ticketId'] == ticket_id
        assert response.payload['metadata'] == ticket_metadata
        
        mock_ticket_service.verify_ticket.assert_called_once_with(ticket_id)
    
    def test_handle_verify_ticket_valid_download(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with valid download ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        ticket_metadata = {
            'type': 'download',
            'fileId': str(uuid.uuid4()),
            'storedName': 'room/file',
            'sha256Whole': 'b' * 64,
            'totalChunks': 20,
            'chunkSize': 524288,
            'expiresAt': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        }
        
        mock_ticket_service.verify_ticket.return_value = (True, ticket_metadata, None)
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.TICKET_VALID
        assert response.request_id == request_id
        assert response.payload['ticketId'] == ticket_id
        assert response.payload['metadata'] == ticket_metadata
    
    def test_handle_verify_ticket_not_found(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with non-existent ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        mock_ticket_service.verify_ticket.return_value = (False, None, 'TICKET_NOT_FOUND')
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.TICKET_INVALID
        assert response.request_id == request_id
        assert response.payload['ticketId'] == ticket_id
        assert response.payload['error']['code'] == 'TICKET_NOT_FOUND'
        assert 'message' in response.payload['error']
    
    def test_handle_verify_ticket_expired(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with expired ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        mock_ticket_service.verify_ticket.return_value = (False, None, 'TICKET_EXPIRED')
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.TICKET_INVALID
        assert response.request_id == request_id
        assert response.payload['ticketId'] == ticket_id
        assert response.payload['error']['code'] == 'TICKET_EXPIRED'
        assert 'message' in response.payload['error']
    
    def test_handle_verify_ticket_missing_ticket_id(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with missing ticketId field."""
        # Arrange
        request_id = str(uuid.uuid4())
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={},  # Missing ticketId
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.ERROR
        assert response.request_id == request_id
        assert response.payload['error']['code'] == 'INVALID_REQUEST'
        assert 'ticketId' in response.payload['error']['message']
        
        # Verify service was not called
        mock_ticket_service.verify_ticket.assert_not_called()
    
    def test_handle_verify_ticket_internal_error(self, ticket_handlers, mock_ticket_service):
        """Test VERIFY_TICKET with internal error."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        mock_ticket_service.verify_ticket.return_value = (False, None, 'INTERNAL_ERROR')
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.type == MessageType.TICKET_INVALID
        assert response.request_id == request_id
        assert response.payload['ticketId'] == ticket_id
        assert response.payload['error']['code'] == 'INTERNAL_ERROR'
    
    def test_handle_verify_ticket_preserves_request_id(self, ticket_handlers, mock_ticket_service):
        """Test that VERIFY_TICKET response preserves request ID."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        ticket_metadata = {
            'type': 'upload',
            'fileId': str(uuid.uuid4()),
            'expiresAt': datetime.now(timezone.utc).isoformat()
        }
        
        mock_ticket_service.verify_ticket.return_value = (True, ticket_metadata, None)
        
        request = Message(
            type=MessageType.VERIFY_TICKET,
            payload={'ticketId': ticket_id},
            request_id=request_id
        )
        
        # Act
        response = ticket_handlers.handle_verify_ticket(request)
        
        # Assert
        assert response.request_id == request_id
