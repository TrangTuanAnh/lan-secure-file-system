"""Integration tests for audit logging in all services."""
import unittest
from unittest.mock import Mock, MagicMock
from auth.auth_service import AuthService
from audit.audit_service import AuditService


class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.users = []
        self.audit_logs = []
    
    def execute_query(self, query, params=None):
        """Mock query execution."""
        if "SELECT id FROM users WHERE username" in query:
            username = params[0] if params else None
            return [u for u in self.users if u['username'] == username]
        elif "SELECT id FROM users WHERE email" in query:
            email = params[0] if params else None
            return [u for u in self.users if u['email'] == email]
        elif "SELECT id, password_hash, global_role FROM users WHERE username" in query:
            username = params[0] if params else None
            return [u for u in self.users if u['username'] == username]
        return []
    
    def execute_update(self, query, params=None):
        """Mock update execution."""
        if "INSERT INTO users" in query:
            user = {
                'id': params[0],
                'username': params[1],
                'email': params[2],
                'password_hash': params[3],
                'global_role': params[4]
            }
            self.users.append(user)
        elif "INSERT INTO audit_logs" in query:
            audit_log = {
                'actor_id': params[0],
                'action': params[1],
                'target_type': params[2],
                'target_id': params[3],
                'room_id': params[4],
                'detail': params[5],
                'status': params[6],
                'created_at': params[7]
            }
            self.audit_logs.append(audit_log)


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.sessions = {}
    
    def set_session(self, token, data, ttl):
        """Mock set session."""
        self.sessions[token] = data
    
    def get_session(self, token):
        """Mock get session."""
        return self.sessions.get(token)
    
    def delete_session(self, token):
        """Mock delete session."""
        if token in self.sessions:
            del self.sessions[token]
            return True
        return False


class TestAuditIntegration(unittest.TestCase):
    """Test audit logging integration in services."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.db = MockDatabase()
        self.redis = MockRedisClient()
        self.audit_service = AuditService(self.db)
        self.auth_service = AuthService(self.db, self.redis, session_ttl=86400, audit_service=self.audit_service)
    
    def test_signup_success_creates_audit_log(self):
        """Test that successful signup creates audit log entry."""
        success, user_id, error_code = self.auth_service.signup(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        
        assert success is True
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'SIGNUP'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == user_id
        assert audit_log['status'] == 'SUCCESS'
        assert audit_log['actor_id'] == user_id
    
    def test_signup_duplicate_username_creates_failed_audit_log(self):
        """Test that failed signup creates audit log with FAILED status."""
        # First signup
        self.auth_service.signup("testuser", "test1@example.com", "password123")
        
        # Clear audit logs
        self.db.audit_logs = []
        
        # Second signup with same username
        success, user_id, error_code = self.auth_service.signup(
            username="testuser",
            email="test2@example.com",
            password="password123"
        )
        
        assert success is False
        assert error_code == "DUPLICATE_USERNAME"
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'SIGNUP'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == 'testuser'
        assert audit_log['status'] == 'FAILED'
        assert audit_log['actor_id'] is None
    
    def test_signup_duplicate_email_creates_failed_audit_log(self):
        """Test that failed signup due to duplicate email creates audit log."""
        # First signup
        self.auth_service.signup("testuser1", "test@example.com", "password123")
        
        # Clear audit logs
        self.db.audit_logs = []
        
        # Second signup with same email
        success, user_id, error_code = self.auth_service.signup(
            username="testuser2",
            email="test@example.com",
            password="password123"
        )
        
        assert success is False
        assert error_code == "DUPLICATE_EMAIL"
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'SIGNUP'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == 'test@example.com'
        assert audit_log['status'] == 'FAILED'
        assert audit_log['actor_id'] is None
    
    def test_login_success_creates_audit_log(self):
        """Test that successful login creates audit log entry."""
        # First signup
        success, user_id, _ = self.auth_service.signup("testuser", "test@example.com", "password123")
        
        # Clear audit logs
        self.db.audit_logs = []
        
        # Login
        success, token, expires_at, error_code = self.auth_service.login("testuser", "password123")
        
        assert success is True
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'LOGIN'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == user_id
        assert audit_log['status'] == 'SUCCESS'
        assert audit_log['actor_id'] == user_id
    
    def test_login_invalid_username_creates_failed_audit_log(self):
        """Test that failed login due to invalid username creates audit log."""
        success, token, expires_at, error_code = self.auth_service.login("nonexistent", "password123")
        
        assert success is False
        assert error_code == "INVALID_CREDENTIALS"
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'LOGIN'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == 'nonexistent'
        assert audit_log['status'] == 'FAILED'
        assert audit_log['actor_id'] is None
    
    def test_login_invalid_password_creates_failed_audit_log(self):
        """Test that failed login due to invalid password creates audit log."""
        # First signup
        success, user_id, _ = self.auth_service.signup("testuser", "test@example.com", "password123")
        
        # Clear audit logs
        self.db.audit_logs = []
        
        # Login with wrong password
        success, token, expires_at, error_code = self.auth_service.login("testuser", "wrongpassword")
        
        assert success is False
        assert error_code == "INVALID_CREDENTIALS"
        assert len(self.db.audit_logs) == 1
        
        audit_log = self.db.audit_logs[0]
        assert audit_log['action'] == 'LOGIN'
        assert audit_log['target_type'] == 'user'
        assert audit_log['target_id'] == user_id
        assert audit_log['status'] == 'FAILED'
        assert audit_log['actor_id'] == user_id


if __name__ == '__main__':
    unittest.main()
