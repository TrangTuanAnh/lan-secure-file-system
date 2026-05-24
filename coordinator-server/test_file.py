"""Tests for file metadata module."""
import pytest
import uuid
from datetime import datetime, timezone
from database import Database
from config import load_config
from file.file_service import FileService
from file.file_handlers import FileHandlers
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from protocol.message import Message
from protocol.message_types import MessageType


@pytest.fixture
def db():
    """Create database connection for tests."""
    config = load_config()
    database = Database(config.database)
    database.connect()
    yield database
    database.close()


@pytest.fixture
def audit_service(db):
    """Create audit service instance."""
    return AuditService(db)


@pytest.fixture
def notification_service():
    """Create notification service instance."""
    return NotificationService()


@pytest.fixture
def file_service(db, audit_service, notification_service):
    """Create file service instance."""
    return FileService(db, audit_service, notification_service)


@pytest.fixture
def file_handlers(file_service):
    """Create file handlers instance."""
    return FileHandlers(file_service)


@pytest.fixture
def test_user(db):
    """Create a test user."""
    user_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, 'testuser', 'test@example.com', 'hash', 'USER')
    )
    yield user_id
    # Cleanup
    db.execute_update("DELETE FROM users WHERE id = %s", (user_id,))


@pytest.fixture
def test_admin(db):
    """Create a test admin user."""
    admin_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (admin_id, 'admin', 'admin@example.com', 'hash', 'ADMIN')
    )
    yield admin_id
    # Cleanup
    db.execute_update("DELETE FROM users WHERE id = %s", (admin_id,))


@pytest.fixture
def test_room(db, test_admin):
    """Create a test room."""
    room_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO rooms (id, name, created_by, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (room_id, 'Test Room', test_admin, datetime.now(timezone.utc))
    )
    # Add admin as OWNER
    db.execute_update(
        """
        INSERT INTO room_members (room_id, user_id, role, added_at)
        VALUES (%s, %s, %s, %s)
        """,
        (room_id, test_admin, 'OWNER', datetime.now(timezone.utc))
    )
    yield room_id
    # Cleanup
    db.execute_update("DELETE FROM room_members WHERE room_id = %s", (room_id,))
    db.execute_update("DELETE FROM rooms WHERE id = %s", (room_id,))


@pytest.fixture
def test_file(db, test_room, test_admin):
    """Create a test file."""
    file_id = str(uuid.uuid4())
    db.execute_update(
        """
        INSERT INTO files (id, room_id, original_name, stored_name, version, uploader_id,
                          size_bytes, mime_type, sha256_whole, total_chunks, chunk_size, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (file_id, test_room, 'test.txt', 'stored/test.txt', 1, test_admin,
         1024, 'text/plain', 'a' * 64, 1, 524288, 'READY', datetime.now(timezone.utc))
    )
    yield file_id
    # Cleanup
    db.execute_update("DELETE FROM files WHERE id = %s", (file_id,))


class TestFileService:
    """Test file service operations."""
    
    def test_list_files_as_member(self, file_service, test_user, test_room, test_file, db):
        """Test listing files as a room member."""
        # Add user as MEMBER
        db.execute_update(
            """
            INSERT INTO room_members (room_id, user_id, role, added_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_room, test_user, 'MEMBER', datetime.now(timezone.utc))
        )
        
        success, files_list, error_code = file_service.list_files(test_user, 'USER', test_room)
        
        assert success is True
        assert error_code is None
        assert len(files_list) == 1
        assert files_list[0]['fileId'] == test_file
        assert files_list[0]['originalName'] == 'test.txt'
        assert files_list[0]['status'] == 'READY'
        
        # Cleanup
        db.execute_update("DELETE FROM room_members WHERE room_id = %s AND user_id = %s", (test_room, test_user))
    
    def test_list_files_as_admin(self, file_service, test_admin, test_room, test_file):
        """Test listing files as ADMIN."""
        success, files_list, error_code = file_service.list_files(test_admin, 'ADMIN', test_room)
        
        assert success is True
        assert error_code is None
        assert len(files_list) == 1
        assert files_list[0]['fileId'] == test_file
    
    def test_list_files_permission_denied(self, file_service, test_user, test_room):
        """Test listing files without permission."""
        success, files_list, error_code = file_service.list_files(test_user, 'USER', test_room)
        
        assert success is False
        assert error_code == 'PERMISSION_DENIED'
        assert files_list is None
    
    def test_list_files_only_ready(self, file_service, test_admin, test_room, db):
        """Test that LIST_FILES only returns READY files."""
        # Create a file with UPLOADING status
        uploading_file_id = str(uuid.uuid4())
        db.execute_update(
            """
            INSERT INTO files (id, room_id, original_name, stored_name, version, uploader_id,
                              size_bytes, mime_type, sha256_whole, total_chunks, chunk_size, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (uploading_file_id, test_room, 'uploading.txt', 'stored/uploading.txt', 1, test_admin,
             1024, 'text/plain', 'b' * 64, 1, 524288, 'UPLOADING', datetime.now(timezone.utc))
        )
        
        success, files_list, error_code = file_service.list_files(test_admin, 'ADMIN', test_room)
        
        assert success is True
        # Should not include the UPLOADING file
        assert all(f['status'] == 'READY' for f in files_list)
        
        # Cleanup
        db.execute_update("DELETE FROM files WHERE id = %s", (uploading_file_id,))
    
    def test_get_file_detail(self, file_service, test_admin, test_file):
        """Test getting file details."""
        success, file_data, error_code = file_service.get_file_detail(test_admin, 'ADMIN', test_file)
        
        assert success is True
        assert error_code is None
        assert file_data['fileId'] == test_file
        assert file_data['originalName'] == 'test.txt'
        assert file_data['sizeBytes'] == 1024
    
    def test_get_file_detail_not_found(self, file_service, test_admin):
        """Test getting details of non-existent file."""
        fake_file_id = str(uuid.uuid4())
        success, file_data, error_code = file_service.get_file_detail(test_admin, 'ADMIN', fake_file_id)
        
        assert success is False
        assert error_code == 'FILE_NOT_FOUND'
        assert file_data is None
    
    def test_get_file_detail_permission_denied(self, file_service, test_user, test_file):
        """Test getting file details without permission."""
        success, file_data, error_code = file_service.get_file_detail(test_user, 'USER', test_file)
        
        assert success is False
        assert error_code == 'PERMISSION_DENIED'
        assert file_data is None
    
    def test_get_file_versions(self, file_service, test_admin, test_room, db):
        """Test getting file versions."""
        # Create multiple versions of the same file
        file_ids = []
        for version in [1, 2, 3]:
            file_id = str(uuid.uuid4())
            db.execute_update(
                """
                INSERT INTO files (id, room_id, original_name, stored_name, version, uploader_id,
                                  size_bytes, mime_type, sha256_whole, total_chunks, chunk_size, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (file_id, test_room, 'versioned.txt', f'stored/versioned_v{version}.txt', version, test_admin,
                 1024, 'text/plain', f'{version}' * 64, 1, 524288, 'READY', datetime.now(timezone.utc))
            )
            file_ids.append(file_id)
        
        success, versions_list, error_code = file_service.get_file_versions(
            test_admin, 'ADMIN', test_room, 'versioned.txt'
        )
        
        assert success is True
        assert error_code is None
        assert len(versions_list) == 3
        # Should be ordered by version descending
        assert versions_list[0]['version'] == 3
        assert versions_list[1]['version'] == 2
        assert versions_list[2]['version'] == 1
        
        # Cleanup
        for file_id in file_ids:
            db.execute_update("DELETE FROM files WHERE id = %s", (file_id,))
    
    def test_delete_file_as_owner(self, file_service, test_admin, test_file, db):
        """Test deleting file as OWNER."""
        success, error_code = file_service.delete_file(test_admin, 'ADMIN', test_file)
        
        assert success is True
        assert error_code is None
        
        # Verify file status is DELETED
        files = db.execute_query("SELECT status FROM files WHERE id = %s", (test_file,))
        assert files[0]['status'] == 'DELETED'
    
    def test_delete_file_permission_denied(self, file_service, test_user, test_file, test_room, db):
        """Test deleting file without permission."""
        # Add user as MEMBER (not OWNER)
        db.execute_update(
            """
            INSERT INTO room_members (room_id, user_id, role, added_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_room, test_user, 'MEMBER', datetime.now(timezone.utc))
        )
        
        success, error_code = file_service.delete_file(test_user, 'USER', test_file)
        
        assert success is False
        assert error_code == 'PERMISSION_DENIED'
        
        # Cleanup
        db.execute_update("DELETE FROM room_members WHERE room_id = %s AND user_id = %s", (test_room, test_user))

    def test_uploader_member_can_delete_own_file(self, file_service, test_user, test_room, db):
        """Uploader can delete their own file even without OWNER role."""
        db.execute_update(
            """
            INSERT INTO room_members (room_id, user_id, role, added_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_room, test_user, 'MEMBER', datetime.now(timezone.utc))
        )

        file_id = str(uuid.uuid4())
        db.execute_update(
            """
            INSERT INTO files (id, room_id, original_name, stored_name, version, uploader_id,
                              size_bytes, mime_type, sha256_whole, total_chunks, chunk_size, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (file_id, test_room, 'owned.txt', 'stored/owned.txt', 1, test_user,
             2048, 'text/plain', 'b' * 64, 1, 524288, 'READY', datetime.now(timezone.utc))
        )

        success, error_code = file_service.delete_file(test_user, 'USER', file_id)

        assert success is True
        assert error_code is None

        files = db.execute_query("SELECT status FROM files WHERE id = %s", (file_id,))
        assert files[0]['status'] == 'DELETED'

        db.execute_update("DELETE FROM room_members WHERE room_id = %s AND user_id = %s", (test_room, test_user))
        db.execute_update("DELETE FROM files WHERE id = %s", (file_id,))
    
    def test_calculate_next_version_first_file(self, file_service, test_room):
        """Test calculating version for first file."""
        version = file_service.calculate_next_version(test_room, 'newfile.txt')
        assert version == 1
    
    def test_calculate_next_version_increment(self, file_service, test_room, test_admin, db):
        """Test calculating version for existing file."""
        # Create a file with version 1
        file_id = str(uuid.uuid4())
        db.execute_update(
            """
            INSERT INTO files (id, room_id, original_name, stored_name, version, uploader_id,
                              size_bytes, mime_type, sha256_whole, total_chunks, chunk_size, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (file_id, test_room, 'existing.txt', 'stored/existing.txt', 1, test_admin,
             1024, 'text/plain', 'c' * 64, 1, 524288, 'READY', datetime.now(timezone.utc))
        )
        
        version = file_service.calculate_next_version(test_room, 'existing.txt')
        assert version == 2
        
        # Cleanup
        db.execute_update("DELETE FROM files WHERE id = %s", (file_id,))


class TestFileHandlers:
    """Test file handlers."""
    
    def test_handle_list_files(self, file_handlers, test_admin, test_room, test_file):
        """Test LIST_FILES handler."""
        message = Message(
            type=MessageType.LIST_FILES,
            payload={'roomId': test_room},
            request_id='test-request-1'
        )
        
        response = file_handlers.handle_list_files(message, test_admin, 'ADMIN')
        
        assert response.type == MessageType.LIST_FILES_RESPONSE
        assert response.request_id == 'test-request-1'
        assert 'files' in response.payload
        assert len(response.payload['files']) == 1
    
    def test_handle_list_files_missing_room_id(self, file_handlers, test_admin):
        """Test LIST_FILES handler with missing roomId."""
        message = Message(
            type=MessageType.LIST_FILES,
            payload={},
            request_id='test-request-2'
        )
        
        response = file_handlers.handle_list_files(message, test_admin, 'ADMIN')
        
        assert response.type == MessageType.ERROR
        assert response.payload['error']['code'] == 'INVALID_INPUT'
    
    def test_handle_file_detail(self, file_handlers, test_admin, test_file):
        """Test FILE_DETAIL handler."""
        message = Message(
            type=MessageType.FILE_DETAIL,
            payload={'fileId': test_file},
            request_id='test-request-3'
        )
        
        response = file_handlers.handle_file_detail(message, test_admin, 'ADMIN')
        
        assert response.type == MessageType.FILE_DETAIL_RESPONSE
        assert response.request_id == 'test-request-3'
        assert response.payload['fileId'] == test_file
    
    def test_handle_file_versions(self, file_handlers, test_admin, test_room):
        """Test FILE_VERSIONS handler."""
        message = Message(
            type=MessageType.FILE_VERSIONS,
            payload={'roomId': test_room, 'originalName': 'test.txt'},
            request_id='test-request-4'
        )
        
        response = file_handlers.handle_file_versions(message, test_admin, 'ADMIN')
        
        assert response.type == MessageType.FILE_VERSIONS_RESPONSE
        assert response.request_id == 'test-request-4'
        assert 'versions' in response.payload
    
    def test_handle_delete_file(self, file_handlers, test_admin, test_file):
        """Test DELETE_FILE handler."""
        message = Message(
            type=MessageType.DELETE_FILE,
            payload={'fileId': test_file},
            request_id='test-request-5'
        )
        
        response = file_handlers.handle_delete_file(message, test_admin, 'ADMIN')
        
        assert response.type == MessageType.DELETE_FILE_RESPONSE
        assert response.request_id == 'test-request-5'
        assert response.payload['success'] is True
        assert response.payload['fileId'] == test_file


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
