"""Tests for authentication module."""
import pytest
import uuid
from datetime import datetime, timezone
from auth.password_hasher import PasswordHasher
from auth.auth_service import AuthService
from auth.auth_handlers import AuthHandlers
from protocol.message import Message
from protocol.message_types import MessageType


class TestPasswordHasher:
    """Tests for PasswordHasher class."""
    
    def test_hash_password(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = PasswordHasher.hash(password)
        
        # Hash should be a string
        assert isinstance(hashed, str)
        # Hash should start with bcrypt prefix
        assert hashed.startswith('$2b$')
        # Hash should contain cost factor 12
        assert '$2b$12$' in hashed
    
    def test_verify_correct_password(self):
        """Test password verification with correct password."""
        password = "test_password_123"
        hashed = PasswordHasher.hash(password)
        
        # Correct password should verify
        assert PasswordHasher.verify(password, hashed) is True
    
    def test_verify_incorrect_password(self):
        """Test password verification with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = PasswordHasher.hash(password)
        
        # Wrong password should not verify
        assert PasswordHasher.verify(wrong_password, hashed) is False
    
    def test_hash_empty_password_raises_error(self):
        """Test that hashing empty password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            PasswordHasher.hash("")
    
    def test_verify_empty_password_returns_false(self):
        """Test that verifying empty password returns False."""
        hashed = PasswordHasher.hash("test")
        assert PasswordHasher.verify("", hashed) is False
    
    def test_verify_empty_hash_returns_false(self):
        """Test that verifying against empty hash returns False."""
        assert PasswordHasher.verify("test", "") is False


class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.users = []
    
    def execute_query(self, query: str, params: tuple = None):
        """Mock query execution."""
        if "SELECT id FROM users WHERE username" in query:
            username = params[0]
            return [u for u in self.users if u.get('username') == username]
        elif "SELECT id FROM users WHERE email" in query:
            email = params[0]
            return [u for u in self.users if u.get('email') == email]
        elif "SELECT id, password_hash, global_role FROM users WHERE username" in query:
            username = params[0]
            return [u for u in self.users if u.get('username') == username]
        return []
    
    def execute_update(self, query: str, params: tuple = None):
        """Mock update execution."""
        if "INSERT INTO users" in query:
            user_id, username, email, password_hash, global_role, created_at, updated_at = params
            self.users.append({
                'id': user_id,
                'username': username,
                'email': email,
                'password_hash': password_hash,
                'global_role': global_role,
                'created_at': created_at,
                'updated_at': updated_at
            })
            return 1
        return 0


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.sessions = {}
    
    def set_session(self, token: str, user_data: dict, ttl_seconds: int):
        """Mock session storage."""
        self.sessions[token] = user_data
    
    def get_session(self, token: str):
        """Mock session retrieval."""
        return self.sessions.get(token)
    
    def delete_session(self, token: str):
        """Mock session deletion."""
        if token in self.sessions:
            del self.sessions[token]
            return True
        return False


class TestAuthService:
    """Tests for AuthService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.db = MockDatabase()
        self.redis = MockRedisClient()
        self.auth_service = AuthService(self.db, self.redis, session_ttl=86400)
    
    def test_signup_success(self):
        """Test successful user signup."""
        success, user_id, error_code = self.auth_service.signup(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        
        assert success is True
        assert user_id is not None
        assert error_code is None
        assert len(self.db.users) == 1
        assert self.db.users[0]['username'] == "testuser"
        assert self.db.users[0]['email'] == "test@example.com"
    
    def test_signup_duplicate_username(self):
        """Test signup with duplicate username."""
        # First signup
        self.auth_service.signup("testuser", "test1@example.com", "password123")
        
        # Second signup with same username
        success, user_id, error_code = self.auth_service.signup(
            username="testuser",
            email="test2@example.com",
            password="password123"
        )
        
        assert success is False
        assert user_id is None
        assert error_code == "DUPLICATE_USERNAME"
    
    def test_signup_duplicate_email(self):
        """Test signup with duplicate email."""
        # First signup
        self.auth_service.signup("testuser1", "test@example.com", "password123")
        
        # Second signup with same email
        success, user_id, error_code = self.auth_service.signup(
            username="testuser2",
            email="test@example.com",
            password="password123"
        )
        
        assert success is False
        assert user_id is None
        assert error_code == "DUPLICATE_EMAIL"
    
    def test_login_success(self):
        """Test successful login."""
        # Create user
        self.auth_service.signup("testuser", "test@example.com", "password123")
        
        # Login
        success, token, expires_at, error_code = self.auth_service.login(
            username="testuser",
            password="password123"
        )
        
        assert success is True
        assert token is not None
        assert expires_at is not None
        assert error_code is None
        assert token in self.redis.sessions
    
    def test_login_invalid_username(self):
        """Test login with invalid username."""
        success, token, expires_at, error_code = self.auth_service.login(
            username="nonexistent",
            password="password123"
        )
        
        assert success is False
        assert token is None
        assert error_code == "INVALID_CREDENTIALS"
    
    def test_login_invalid_password(self):
        """Test login with invalid password."""
        # Create user
        self.auth_service.signup("testuser", "test@example.com", "password123")
        
        # Login with wrong password
        success, token, expires_at, error_code = self.auth_service.login(
            username="testuser",
            password="wrongpassword"
        )
        
        assert success is False
        assert token is None
        assert error_code == "INVALID_CREDENTIALS"
    
    def test_validate_token_success(self):
        """Test successful token validation."""
        # Create user and login
        self.auth_service.signup("testuser", "test@example.com", "password123")
        success, token, _, _ = self.auth_service.login("testuser", "password123")
        
        # Validate token
        valid, session_data, error_code = self.auth_service.validate_token(token)
        
        assert valid is True
        assert session_data is not None
        assert 'userId' in session_data
        assert 'globalRole' in session_data
        assert error_code is None
    
    def test_validate_token_invalid(self):
        """Test validation of invalid token."""
        valid, session_data, error_code = self.auth_service.validate_token("invalid_token")
        
        assert valid is False
        assert session_data is None
        assert error_code == "INVALID_TOKEN"
    
    def test_logout_success(self):
        """Test successful logout."""
        # Create user and login
        self.auth_service.signup("testuser", "test@example.com", "password123")
        success, token, _, _ = self.auth_service.login("testuser", "password123")
        
        # Logout
        success, error_code = self.auth_service.logout(token)
        
        assert success is True
        assert error_code is None
        assert token not in self.redis.sessions
    
    def test_logout_removes_session(self):
        """Test that logout removes session from Redis."""
        # Create user and login
        self.auth_service.signup("testuser", "test@example.com", "password123")
        success, token, _, _ = self.auth_service.login("testuser", "password123")
        
        # Verify session exists
        assert token in self.redis.sessions
        
        # Logout
        self.auth_service.logout(token)
        
        # Verify session is removed
        assert token not in self.redis.sessions


class TestAuthHandlers:
    """Tests for AuthHandlers class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.db = MockDatabase()
        self.redis = MockRedisClient()
        self.auth_service = AuthService(self.db, self.redis, session_ttl=86400)
        self.handlers = AuthHandlers(self.auth_service)
    
    def test_handle_signup_success(self):
        """Test successful signup handler."""
        message = Message.create_request(
            message_type=MessageType.SIGNUP,
            payload={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        
        response = self.handlers.handle_signup(message)
        
        assert response.type == MessageType.SIGNUP_RESPONSE
        assert response.payload['userId'] is not None
        assert response.payload['username'] == "testuser"
        assert response.payload['email'] == "test@example.com"
    
    def test_handle_signup_duplicate_username(self):
        """Test signup handler with duplicate username."""
        # First signup
        message1 = Message.create_request(
            message_type=MessageType.SIGNUP,
            payload={
                "username": "testuser",
                "email": "test1@example.com",
                "password": "password123"
            }
        )
        self.handlers.handle_signup(message1)
        
        # Second signup with same username
        message2 = Message.create_request(
            message_type=MessageType.SIGNUP,
            payload={
                "username": "testuser",
                "email": "test2@example.com",
                "password": "password123"
            }
        )
        response = self.handlers.handle_signup(message2)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "DUPLICATE_USERNAME"
    
    def test_handle_login_success(self):
        """Test successful login handler."""
        # Create user
        signup_msg = Message.create_request(
            message_type=MessageType.SIGNUP,
            payload={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        self.handlers.handle_signup(signup_msg)
        
        # Login
        login_msg = Message.create_request(
            message_type=MessageType.LOGIN,
            payload={
                "username": "testuser",
                "password": "password123"
            }
        )
        response = self.handlers.handle_login(login_msg)
        
        assert response.type == MessageType.LOGIN_RESPONSE
        assert 'token' in response.payload
        assert 'expiresAt' in response.payload
    
    def test_handle_login_invalid_credentials(self):
        """Test login handler with invalid credentials."""
        message = Message.create_request(
            message_type=MessageType.LOGIN,
            payload={
                "username": "nonexistent",
                "password": "password123"
            }
        )
        response = self.handlers.handle_login(message)
        
        assert response.type == MessageType.ERROR
        assert response.get_error_code() == "INVALID_CREDENTIALS"
    
    def test_handle_logout_success(self):
        """Test successful logout handler."""
        # Create user and login
        signup_msg = Message.create_request(
            message_type=MessageType.SIGNUP,
            payload={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        self.handlers.handle_signup(signup_msg)
        
        login_msg = Message.create_request(
            message_type=MessageType.LOGIN,
            payload={
                "username": "testuser",
                "password": "password123"
            }
        )
        login_response = self.handlers.handle_login(login_msg)
        token = login_response.payload['token']
        
        # Logout
        logout_msg = Message.create_request(
            message_type=MessageType.LOGOUT,
            payload={"token": token}
        )
        response = self.handlers.handle_logout(logout_msg)
        
        assert response.type == MessageType.LOGOUT_RESPONSE
        assert response.payload['success'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
