"""Tests for ticket management service."""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock
from ticket.ticket_service import TicketService


class TestTicketService:
    """Test suite for TicketService."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = Mock()
        redis.set_ticket = Mock()
        redis.get_ticket = Mock()
        redis.delete_ticket = Mock()
        return redis
    
    @pytest.fixture
    def ticket_service(self, mock_redis):
        """Create TicketService instance with mock Redis."""
        return TicketService(
            redis_client=mock_redis,
            upload_ticket_ttl_seconds=1800,  # 30 minutes
            download_ticket_ttl_seconds=900   # 15 minutes
        )
    
    def test_generate_upload_ticket(self, ticket_service, mock_redis):
        """Test upload ticket generation."""
        # Arrange
        file_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        total_chunks = 10
        chunk_size = 524288
        sha256_whole = "a" * 64
        stored_name = f"{room_id}/{file_id}"
        
        # Act
        ticket_id = ticket_service.generate_upload_ticket(
            file_id=file_id,
            user_id=user_id,
            room_id=room_id,
            total_chunks=total_chunks,
            chunk_size=chunk_size,
            sha256_whole=sha256_whole,
            stored_name=stored_name
        )
        
        # Assert
        assert ticket_id is not None
        assert isinstance(ticket_id, str)
        
        # Verify Redis was called
        mock_redis.set_ticket.assert_called_once()
        call_args = mock_redis.set_ticket.call_args
        
        # Check ticket ID
        assert call_args[0][0] == ticket_id
        
        # Check ticket data
        ticket_data = call_args[0][1]
        assert ticket_data['type'] == 'upload'
        assert ticket_data['fileId'] == file_id
        assert ticket_data['userId'] == user_id
        assert ticket_data['roomId'] == room_id
        assert ticket_data['totalChunks'] == total_chunks
        assert ticket_data['chunkSize'] == chunk_size
        assert ticket_data['sha256Whole'] == sha256_whole
        assert ticket_data['storedName'] == stored_name
        assert 'expiresAt' in ticket_data
        
        # Check TTL
        assert call_args[0][2] == 1800  # 30 minutes
    
    def test_generate_download_ticket(self, ticket_service, mock_redis):
        """Test download ticket generation."""
        # Arrange
        file_id = str(uuid.uuid4())
        stored_name = f"room/{file_id}"
        sha256_whole = "b" * 64
        total_chunks = 20
        chunk_size = 524288
        
        # Act
        ticket_id = ticket_service.generate_download_ticket(
            file_id=file_id,
            stored_name=stored_name,
            sha256_whole=sha256_whole,
            total_chunks=total_chunks,
            chunk_size=chunk_size
        )
        
        # Assert
        assert ticket_id is not None
        assert isinstance(ticket_id, str)
        
        # Verify Redis was called
        mock_redis.set_ticket.assert_called_once()
        call_args = mock_redis.set_ticket.call_args
        
        # Check ticket ID
        assert call_args[0][0] == ticket_id
        
        # Check ticket data
        ticket_data = call_args[0][1]
        assert ticket_data['type'] == 'download'
        assert ticket_data['fileId'] == file_id
        assert ticket_data['storedName'] == stored_name
        assert ticket_data['sha256Whole'] == sha256_whole
        assert ticket_data['totalChunks'] == total_chunks
        assert ticket_data['chunkSize'] == chunk_size
        assert 'expiresAt' in ticket_data
        
        # Check TTL
        assert call_args[0][2] == 900  # 15 minutes
    
    def test_verify_ticket_valid(self, ticket_service, mock_redis):
        """Test verifying a valid ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        ticket_data = {
            'type': 'upload',
            'fileId': str(uuid.uuid4()),
            'userId': str(uuid.uuid4()),
            'roomId': str(uuid.uuid4()),
            'totalChunks': 10,
            'chunkSize': 524288,
            'sha256Whole': "a" * 64,
            'storedName': "room/file",
            'expiresAt': expires_at.isoformat()
        }
        
        mock_redis.get_ticket.return_value = ticket_data
        
        # Act
        is_valid, metadata, error_code = ticket_service.verify_ticket(ticket_id)
        
        # Assert
        assert is_valid is True
        assert metadata == ticket_data
        assert error_code is None
        
        mock_redis.get_ticket.assert_called_once_with(ticket_id)
    
    def test_verify_ticket_not_found(self, ticket_service, mock_redis):
        """Test verifying a non-existent ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        mock_redis.get_ticket.return_value = None
        
        # Act
        is_valid, metadata, error_code = ticket_service.verify_ticket(ticket_id)
        
        # Assert
        assert is_valid is False
        assert metadata is None
        assert error_code == "TICKET_NOT_FOUND"
        
        mock_redis.get_ticket.assert_called_once_with(ticket_id)
    
    def test_verify_ticket_expired(self, ticket_service, mock_redis):
        """Test verifying an expired ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)  # Expired 5 minutes ago
        
        ticket_data = {
            'type': 'download',
            'fileId': str(uuid.uuid4()),
            'storedName': "room/file",
            'sha256Whole': "b" * 64,
            'totalChunks': 20,
            'chunkSize': 524288,
            'expiresAt': expires_at.isoformat()
        }
        
        mock_redis.get_ticket.return_value = ticket_data
        
        # Act
        is_valid, metadata, error_code = ticket_service.verify_ticket(ticket_id)
        
        # Assert
        assert is_valid is False
        assert metadata is None
        assert error_code == "TICKET_EXPIRED"
        
        # Verify expired ticket was deleted
        mock_redis.delete_ticket.assert_called_once_with(ticket_id)
    
    def test_delete_ticket_success(self, ticket_service, mock_redis):
        """Test manually deleting a ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        mock_redis.delete_ticket.return_value = True
        
        # Act
        deleted = ticket_service.delete_ticket(ticket_id)
        
        # Assert
        assert deleted is True
        mock_redis.delete_ticket.assert_called_once_with(ticket_id)
    
    def test_delete_ticket_not_found(self, ticket_service, mock_redis):
        """Test deleting a non-existent ticket."""
        # Arrange
        ticket_id = str(uuid.uuid4())
        mock_redis.delete_ticket.return_value = False
        
        # Act
        deleted = ticket_service.delete_ticket(ticket_id)
        
        # Assert
        assert deleted is False
        mock_redis.delete_ticket.assert_called_once_with(ticket_id)
    
    def test_upload_ticket_ttl_configuration(self):
        """Test custom upload ticket TTL configuration."""
        # Arrange
        mock_redis = Mock()
        custom_ttl = 3600  # 1 hour
        
        service = TicketService(
            redis_client=mock_redis,
            upload_ticket_ttl_seconds=custom_ttl,
            download_ticket_ttl_seconds=900
        )
        
        # Act
        service.generate_upload_ticket(
            file_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            room_id=str(uuid.uuid4()),
            total_chunks=10,
            chunk_size=524288,
            sha256_whole="a" * 64,
            stored_name="room/file"
        )
        
        # Assert
        call_args = mock_redis.set_ticket.call_args
        assert call_args[0][2] == custom_ttl
    
    def test_download_ticket_ttl_configuration(self):
        """Test custom download ticket TTL configuration."""
        # Arrange
        mock_redis = Mock()
        custom_ttl = 600  # 10 minutes
        
        service = TicketService(
            redis_client=mock_redis,
            upload_ticket_ttl_seconds=1800,
            download_ticket_ttl_seconds=custom_ttl
        )
        
        # Act
        service.generate_download_ticket(
            file_id=str(uuid.uuid4()),
            stored_name="room/file",
            sha256_whole="b" * 64,
            total_chunks=20,
            chunk_size=524288
        )
        
        # Assert
        call_args = mock_redis.set_ticket.call_args
        assert call_args[0][2] == custom_ttl
    
    def test_ticket_id_uniqueness(self, ticket_service, mock_redis):
        """Test that generated ticket IDs are unique."""
        # Act
        ticket_id_1 = ticket_service.generate_upload_ticket(
            file_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            room_id=str(uuid.uuid4()),
            total_chunks=10,
            chunk_size=524288,
            sha256_whole="a" * 64,
            stored_name="room/file1"
        )
        
        ticket_id_2 = ticket_service.generate_upload_ticket(
            file_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            room_id=str(uuid.uuid4()),
            total_chunks=10,
            chunk_size=524288,
            sha256_whole="b" * 64,
            stored_name="room/file2"
        )
        
        # Assert
        assert ticket_id_1 != ticket_id_2
