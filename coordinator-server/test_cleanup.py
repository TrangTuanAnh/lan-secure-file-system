"""Tests for cleanup service."""
import pytest
import time
from datetime import datetime, timedelta
from uuid import uuid4
from cleanup import CleanupService


class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.files = []
        self.cursor_context = None
    
    def get_cursor(self):
        """Mock cursor context manager."""
        class MockCursor:
            def __init__(self, db):
                self.db = db
                self.results = []
            
            def execute(self, query, params=None):
                """Mock execute."""
                if "UPDATE files" in query and "status = 'DELETED'" in query:
                    # Find orphaned uploads (UPLOADING status, created > 1 hour ago)
                    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                    orphaned = [
                        f for f in self.db.files
                        if f['status'] == 'UPLOADING' and f['created_at'] < one_hour_ago
                    ]
                    # Update status to DELETED
                    for f in orphaned:
                        f['status'] = 'DELETED'
                    # Store results for fetchall
                    self.results = [{'id': f['id']} for f in orphaned]
            
            def fetchall(self):
                """Mock fetchall."""
                return self.results
            
            def __enter__(self):
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        class MockCursorContext:
            def __init__(self, db):
                self.db = db
            
            def __enter__(self):
                return MockCursor(self.db)
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        return MockCursorContext(self)


@pytest.fixture
def mock_db():
    """Provide mock database instance."""
    return MockDatabase()


@pytest.fixture
def cleanup_service(mock_db):
    """Provide cleanup service instance."""
    service = CleanupService(mock_db, interval_seconds=1)  # Short interval for testing
    yield service
    service.stop()


def create_test_file(db, room_id, user_id, status='UPLOADING', created_at=None):
    """Helper to create a test file record."""
    file_id = uuid4()
    file_record = {
        'id': file_id,
        'room_id': room_id,
        'original_name': 'test_file.txt',
        'stored_name': f'stored/{file_id}',
        'version': 1,
        'uploader_id': user_id,
        'size_bytes': 1024,
        'mime_type': 'text/plain',
        'sha256_whole': 'a' * 64,
        'total_chunks': 1,
        'chunk_size': 524288,
        'status': status,
        'created_at': created_at or datetime.utcnow()
    }
    db.files.append(file_record)
    return file_id


def test_cleanup_orphaned_uploads(mock_db, cleanup_service):
    """Test cleanup identifies and removes orphaned uploads."""
    user_id = uuid4()
    room_id = uuid4()
    
    # Create orphaned upload (created 2 hours ago)
    old_time = datetime.utcnow() - timedelta(hours=2)
    orphaned_file_id = create_test_file(mock_db, room_id, user_id, status='UPLOADING', created_at=old_time)
    
    # Create recent upload (created 30 minutes ago)
    recent_time = datetime.utcnow() - timedelta(minutes=30)
    recent_file_id = create_test_file(mock_db, room_id, user_id, status='UPLOADING', created_at=recent_time)
    
    # Create completed upload (should not be affected)
    completed_file_id = create_test_file(mock_db, room_id, user_id, status='READY', created_at=old_time)
    
    # Run cleanup
    count = cleanup_service.cleanup_orphaned_uploads()
    
    # Verify only orphaned upload was cleaned
    assert count == 1
    
    # Check orphaned file is now DELETED
    orphaned_file = [f for f in mock_db.files if f['id'] == orphaned_file_id][0]
    assert orphaned_file['status'] == 'DELETED'
    
    # Check recent upload is still UPLOADING
    recent_file = [f for f in mock_db.files if f['id'] == recent_file_id][0]
    assert recent_file['status'] == 'UPLOADING'
    
    # Check completed upload is still READY
    completed_file = [f for f in mock_db.files if f['id'] == completed_file_id][0]
    assert completed_file['status'] == 'READY'


def test_cleanup_no_orphaned_uploads(mock_db, cleanup_service):
    """Test cleanup handles case with no orphaned uploads."""
    user_id = uuid4()
    room_id = uuid4()
    
    # Create only recent uploads
    recent_time = datetime.utcnow() - timedelta(minutes=30)
    create_test_file(mock_db, room_id, user_id, status='UPLOADING', created_at=recent_time)
    
    # Run cleanup
    count = cleanup_service.cleanup_orphaned_uploads()
    
    # Verify no files were cleaned
    assert count == 0


def test_cleanup_service_start_stop(cleanup_service):
    """Test cleanup service can be started and stopped."""
    # Start service
    cleanup_service.start()
    assert cleanup_service._running is True
    
    # Wait a bit
    time.sleep(0.5)
    
    # Stop service
    cleanup_service.stop()
    assert cleanup_service._running is False


def test_cleanup_service_background_execution(mock_db, cleanup_service):
    """Test cleanup service runs automatically in background."""
    user_id = uuid4()
    room_id = uuid4()
    
    # Create orphaned upload
    old_time = datetime.utcnow() - timedelta(hours=2)
    orphaned_file_id = create_test_file(mock_db, room_id, user_id, status='UPLOADING', created_at=old_time)
    
    # Start service (interval is 1 second for testing)
    cleanup_service.start()
    
    # Wait for cleanup to run
    time.sleep(2)
    
    # Stop service
    cleanup_service.stop()
    
    # Verify orphaned file was cleaned
    orphaned_file = [f for f in mock_db.files if f['id'] == orphaned_file_id][0]
    assert orphaned_file['status'] == 'DELETED'


def test_cleanup_multiple_orphaned_uploads(mock_db, cleanup_service):
    """Test cleanup handles multiple orphaned uploads."""
    user_id = uuid4()
    room_id = uuid4()
    
    # Create multiple orphaned uploads
    old_time = datetime.utcnow() - timedelta(hours=2)
    file_ids = []
    for i in range(5):
        file_id = create_test_file(mock_db, room_id, user_id, status='UPLOADING', created_at=old_time)
        file_ids.append(file_id)
    
    # Run cleanup
    count = cleanup_service.cleanup_orphaned_uploads()
    
    # Verify all orphaned uploads were cleaned
    assert count == 5
    
    # Check all files are now DELETED
    for file_id in file_ids:
        file_record = [f for f in mock_db.files if f['id'] == file_id][0]
        assert file_record['status'] == 'DELETED'
