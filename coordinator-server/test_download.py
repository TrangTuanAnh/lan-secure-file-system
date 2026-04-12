"""Tests for download control module."""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from database import Database
from redis_client import RedisClient
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from download.download_service import DownloadService
from config import load_config


@pytest.fixture
def config():
    """Load test configuration."""
    return load_config()


@pytest.fixture
def database(config):
    """Create database connection."""
    db = Database(config.database)
    db.connect()
    yield db
    db.close()


@pytest.fixture
def redis_client(config):
    """Create Redis client."""
    redis = RedisClient(config.redis)
    redis.connect()
    yield redis
    redis.close()


@pytest.fixture
def authorization_service(database):
    """Create authorization service."""
    return AuthorizationService(database)


@pytest.fixture
def audit_service(database):
    """Create audit service."""
    return AuditService(database)


@pytest.fixture
def download_service(database, redis_client, authorization_service, audit_service):
    """Create download service."""
    return DownloadService(
        database=database,
        redis_client=redis_client,
        authorization_service=authorization_service,
        audit_service=audit_service,
        ticket_ttl_seconds=900,
        storage_address="localhost:9000"
    )


@pytest.fixture
def test_user(database):
    """Create a test user."""
    user_id = str(uuid.uuid4())
    database.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, 'testuser', 'test@example.com', 'hash', 'USER', 
         datetime.now(timezone.utc), datetime.now(timezone.utc))
    )
    yield user_id
    # Cleanup
    database.execute_update("DELETE FROM users WHERE id = %s", (user_id,))


@pytest.fixture
def test_admin(database):
    """Create a test admin user."""
    admin_id = str(uuid.uuid4())
    database.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (admin_id, 'adminuser', 'admin@example.com', 'hash', 'ADMIN',
         datetime.now(timezone.utc), datetime.now(timezone.utc))
    )
    yield admin_id
    # Cleanup
    database.execute_update("DELETE FROM users WHERE id = %s", (admin_id,))


@pytest.fixture
def test_room(database, test_user):
    """Create a test room."""
    room_id = str(uuid.uuid4())
    database.execute_update(
        """
        INSERT INTO rooms (id, name, created_by, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (room_id, 'Test Room', test_user, datetime.now(timezone.utc))
    )
    # Add creator as OWNER
    database.execute_update(
        """
        INSERT INTO room_members (room_id, user_id, role, added_at)
        VALUES (%s, %s, %s, %s)
        """,
        (room_id, test_user, 'OWNER', datetime.now(timezone.utc))
    )
    yield room_id
    # Cleanup
    database.execute_update("DELETE FROM room_members WHERE room_id = %s", (room_id,))
    database.execute_update("DELETE FROM rooms WHERE id = %s", (room_id,))


@pytest.fixture
def test_file(database, test_room, test_user):
    """Create a test file."""
    file_id = str(uuid.uuid4())
    database.execute_update(
        """
        INSERT INTO files (
            id, room_id, original_name, stored_name, version,
            uploader_id, size_bytes, mime_type, sha256_whole,
            total_chunks, chunk_size, status, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            file_id, test_room, 'test.txt', f'{test_room}/{file_id}', 1,
            test_user, 1024, 'text/plain', 'a' * 64,
            2, 524288, 'READY', datetime.now(timezone.utc)
        )
    )
    yield file_id
    # Cleanup
    database.execute_update("DELETE FROM files WHERE id = %s", (file_id,))


class TestDownloadDirect:
    """Tests for direct download with access token."""
    
    def test_init_download_success(self, download_service, test_user, test_file):
        """Test successful download initialization with direct permission."""
        success, download_plan, error = download_service.handle_init_download_direct(
            user_id=test_user,
            global_role='USER',
            file_id=test_file
        )
        
        assert success is True
        assert error is None
        assert download_plan is not None
        assert 'ticket' in download_plan
        assert 'storageAddress' in download_plan
        assert 'fileName' in download_plan
        assert download_plan['fileName'] == 'test.txt'
        assert download_plan['fileSize'] == 1024
        assert download_plan['totalChunks'] == 2
    
    def test_init_download_permission_denied(self, download_service, test_file, database):
        """Test download denied for user without permission."""
        # Create another user not in the room
        other_user_id = str(uuid.uuid4())
        database.execute_update(
            """
            INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (other_user_id, 'otheruser', 'other@example.com', 'hash', 'USER',
             datetime.now(timezone.utc), datetime.now(timezone.utc))
        )
        
        success, download_plan, error = download_service.handle_init_download_direct(
            user_id=other_user_id,
            global_role='USER',
            file_id=test_file
        )
        
        assert success is False
        assert error == 'PERMISSION_DENIED'
        assert download_plan is None
        
        # Cleanup
        database.execute_update("DELETE FROM users WHERE id = %s", (other_user_id,))
    
    def test_init_download_admin_access(self, download_service, test_admin, test_file):
        """Test ADMIN can download any file."""
        success, download_plan, error = download_service.handle_init_download_direct(
            user_id=test_admin,
            global_role='ADMIN',
            file_id=test_file
        )
        
        assert success is True
        assert error is None
        assert download_plan is not None
    
    def test_init_download_file_not_found(self, download_service, test_user):
        """Test download with non-existent file."""
        fake_file_id = str(uuid.uuid4())
        
        success, download_plan, error = download_service.handle_init_download_direct(
            user_id=test_user,
            global_role='USER',
            file_id=fake_file_id
        )
        
        assert success is False
        assert error == 'FILE_NOT_FOUND'
        assert download_plan is None


class TestShareToken:
    """Tests for share token creation and usage."""
    
    def test_create_share_token_success(self, download_service, test_user, test_file):
        """Test successful share token creation."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=5,
            expires_at=expires_at
        )
        
        assert success is True
        assert error is None
        assert token is not None
        assert len(token) == 64  # 32 bytes hex = 64 characters
    
    def test_create_share_token_permission_denied(self, download_service, test_file, database):
        """Test share token creation denied for user without permission."""
        # Create another user not in the room
        other_user_id = str(uuid.uuid4())
        database.execute_update(
            """
            INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (other_user_id, 'otheruser', 'other@example.com', 'hash', 'USER',
             datetime.now(timezone.utc), datetime.now(timezone.utc))
        )
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        success, token, error = download_service.create_share_token(
            user_id=other_user_id,
            global_role='USER',
            file_id=test_file,
            max_downloads=5,
            expires_at=expires_at
        )
        
        assert success is False
        assert error == 'PERMISSION_DENIED'
        assert token is None
        
        # Cleanup
        database.execute_update("DELETE FROM users WHERE id = %s", (other_user_id,))
    
    def test_init_download_with_share_token(self, download_service, test_user, test_file):
        """Test download with valid share token."""
        # Create share token
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=3,
            expires_at=expires_at
        )
        assert success is True
        
        # Use share token to download
        success, download_plan, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        
        assert success is True
        assert error is None
        assert download_plan is not None
        assert 'ticket' in download_plan
    
    def test_share_token_exhaustion(self, download_service, test_user, test_file):
        """Test share token exhaustion after max downloads."""
        # Create share token with max_downloads=2
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=2,
            expires_at=expires_at
        )
        assert success is True
        
        # First download - should succeed
        success, _, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        assert success is True
        
        # Second download - should succeed
        success, _, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        assert success is True
        
        # Third download - should fail (exhausted)
        success, _, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        assert success is False
        assert error == 'SHARE_TOKEN_EXHAUSTED'
    
    def test_share_token_expiration(self, download_service, test_user, test_file):
        """Test share token expiration."""
        # Create share token that expires in the past
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=5,
            expires_at=expires_at
        )
        assert success is True
        
        # Try to use expired token
        success, _, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        assert success is False
        assert error == 'SHARE_TOKEN_EXPIRED'
    
    def test_invalid_share_token(self, download_service, test_file):
        """Test download with invalid share token."""
        fake_token = 'a' * 64
        
        success, _, error = download_service.handle_init_download_share(
            share_token=fake_token,
            file_id=test_file
        )
        assert success is False
        assert error == 'INVALID_SHARE_TOKEN'


class TestTicketGeneration:
    """Tests for download ticket generation."""
    
    def test_ticket_stored_in_redis(self, download_service, redis_client, test_user, test_file):
        """Test that download ticket is stored in Redis."""
        success, download_plan, error = download_service.handle_init_download_direct(
            user_id=test_user,
            global_role='USER',
            file_id=test_file
        )
        
        assert success is True
        ticket = download_plan['ticket']
        
        # Verify ticket exists in Redis
        ticket_data = redis_client.get_ticket(ticket)
        assert ticket_data is not None
        assert ticket_data['type'] == 'download'
        assert ticket_data['fileId'] == test_file
        assert 'storedName' in ticket_data
        assert 'sha256Whole' in ticket_data
        assert 'totalChunks' in ticket_data
        assert 'chunkSize' in ticket_data
        assert 'expiresAt' in ticket_data


class TestAuditLogging:
    """Tests for audit logging."""
    
    def test_download_audit_log(self, download_service, database, test_user, test_file, test_room):
        """Test audit log created for download."""
        success, _, error = download_service.handle_init_download_direct(
            user_id=test_user,
            global_role='USER',
            file_id=test_file
        )
        assert success is True
        
        # Check audit log
        logs = database.execute_query(
            """
            SELECT action, target_type, target_id, room_id, status
            FROM audit_logs
            WHERE actor_id = %s AND action = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (test_user, 'DOWNLOAD')
        )
        
        assert len(logs) == 1
        assert logs[0]['action'] == 'DOWNLOAD'
        assert logs[0]['target_type'] == 'file'
        assert logs[0]['target_id'] == test_file
        assert logs[0]['room_id'] == test_room
        assert logs[0]['status'] == 'SUCCESS'
    
    def test_share_token_creation_audit_log(self, download_service, database, test_user, test_file, test_room):
        """Test audit log created for share token creation."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=5,
            expires_at=expires_at
        )
        assert success is True
        
        # Check audit log
        logs = database.execute_query(
            """
            SELECT action, target_type, room_id, status
            FROM audit_logs
            WHERE actor_id = %s AND action = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (test_user, 'CREATE_SHARE_TOKEN')
        )
        
        assert len(logs) == 1
        assert logs[0]['action'] == 'CREATE_SHARE_TOKEN'
        assert logs[0]['target_type'] == 'share_token'
        assert logs[0]['room_id'] == test_room
        assert logs[0]['status'] == 'SUCCESS'
    
    def test_share_token_usage_audit_log(self, download_service, database, test_user, test_file, test_room):
        """Test audit log created for share token usage."""
        # Create share token
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        success, token, error = download_service.create_share_token(
            user_id=test_user,
            global_role='USER',
            file_id=test_file,
            max_downloads=5,
            expires_at=expires_at
        )
        assert success is True
        
        # Use share token
        success, _, error = download_service.handle_init_download_share(
            share_token=token,
            file_id=test_file
        )
        assert success is True
        
        # Check audit log
        logs = database.execute_query(
            """
            SELECT action, target_type, room_id, status
            FROM audit_logs
            WHERE actor_id = %s AND action = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (test_user, 'USE_SHARE_TOKEN')
        )
        
        assert len(logs) == 1
        assert logs[0]['action'] == 'USE_SHARE_TOKEN'
        assert logs[0]['target_type'] == 'share_token'
        assert logs[0]['room_id'] == test_room
        assert logs[0]['status'] == 'SUCCESS'
