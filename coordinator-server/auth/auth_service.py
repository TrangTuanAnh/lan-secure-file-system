"""Authentication service for user signup, login, logout, and token validation."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from database import Database
from redis_client import RedisClient
from auth.password_hasher import PasswordHasher
from audit.audit_service import AuditService
from logging_config import get_logger

logger = get_logger(__name__)


class AuthService:
    """Handles user authentication operations."""
    
    def __init__(
        self,
        database: Database,
        redis_client: RedisClient,
        session_ttl: int,
        audit_service: Optional[AuditService] = None
    ):
        """
        Initialize authentication service.
        
        Args:
            database: Database instance
            redis_client: Redis client instance
            session_ttl: Session TTL in seconds (default 24 hours)
            audit_service: Optional audit service for logging
        """
        self.db = database
        self.redis = redis_client
        self.session_ttl = session_ttl
        self.password_hasher = PasswordHasher()
        self.audit = audit_service
    
    def signup(self, username: str, email: str, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Register a new user.
        
        Args:
            username: Desired username
            email: User email address
            password: Plain text password
        
        Returns:
            Tuple of (success, user_id, error_code)
            - success: True if signup succeeded
            - user_id: UUID of created user if successful
            - error_code: Error code if failed (DUPLICATE_USERNAME, DUPLICATE_EMAIL)
        """
        # Validate inputs
        if not username or not email or not password:
            return False, None, "INVALID_INPUT"
        
        # Check if username already exists
        existing_user = self.db.execute_query(
            "SELECT id FROM users WHERE username = %s",
            (username,)
        )
        if existing_user:
            logger.info(f"Signup failed: username '{username}' already exists")
            # Write audit log for failed signup
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=None,
                    action='SIGNUP',
                    target_type='user',
                    target_id=username,
                    detail={'username': username, 'email': email, 'reason': 'duplicate_username'},
                    status='FAILED'
                )
            return False, None, "DUPLICATE_USERNAME"
        
        # Check if email already exists
        existing_email = self.db.execute_query(
            "SELECT id FROM users WHERE email = %s",
            (email,)
        )
        if existing_email:
            logger.info(f"Signup failed: email '{email}' already exists")
            # Write audit log for failed signup
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=None,
                    action='SIGNUP',
                    target_type='user',
                    target_id=email,
                    detail={'username': username, 'email': email, 'reason': 'duplicate_email'},
                    status='FAILED'
                )
            return False, None, "DUPLICATE_EMAIL"
        
        # Hash password
        try:
            password_hash = self.password_hasher.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            return False, None, "INTERNAL_ERROR"
        
        # Insert user record
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        try:
            self.db.execute_update(
                """
                INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, username, email, password_hash, 'USER', now, now)
            )
            logger.info(f"User created: {user_id} (username={username})")
            
            # Write audit log for successful signup
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='SIGNUP',
                    target_type='user',
                    target_id=user_id,
                    detail={'username': username, 'email': email},
                    status='SUCCESS'
                )
            
            return True, user_id, None
        except Exception as e:
            logger.error(f"Failed to insert user: {e}")
            return False, None, "DATABASE_ERROR"
    
    def _authenticate_and_create_session(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[Dict[str, Any]], Optional[str]]:
        """
        Authenticate user, create session, and return profile information.

        Returns:
            Tuple of (success, token, expires_at, user_profile, error_code)
        """
        # Query user by username
        users = self.db.execute_query(
            """
            SELECT id, username, email, password_hash, global_role
            FROM users
            WHERE username = %s
            """,
            (username,)
        )
        
        if not users:
            logger.info(f"Login failed: username '{username}' not found")
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=None,
                    action='LOGIN',
                    target_type='user',
                    target_id=username,
                    detail={'username': username, 'reason': 'user_not_found'},
                    status='FAILED'
                )
            return False, None, None, None, "INVALID_CREDENTIALS"
        
        user = users[0]
        user_id = user['id']
        password_hash = user['password_hash']
        global_role = user['global_role']
        
        if not self.password_hasher.verify(password, password_hash):
            logger.info(f"Login failed: invalid password for username '{username}'")
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='LOGIN',
                    target_type='user',
                    target_id=user_id,
                    detail={'username': username, 'reason': 'invalid_password'},
                    status='FAILED'
                )
            return False, None, None, None, "INVALID_CREDENTIALS"
        
        token = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        expires_at = int(datetime.now(timezone.utc).timestamp()) + self.session_ttl
        
        session_data = {
            "userId": user_id,
            "globalRole": global_role,
            "createdAt": created_at
        }
        
        user_profile = {
            "id": user_id,
            "username": user["username"],
            "email": user["email"],
            "globalRole": global_role,
        }
        
        try:
            self.redis.set_session(token, session_data, self.session_ttl)
            logger.info(f"User logged in: {user_id} (username={username})")
            
            if self.audit:
                self.audit.write_audit_log(
                    actor_id=user_id,
                    action='LOGIN',
                    target_type='user',
                    target_id=user_id,
                    detail={'username': username},
                    status='SUCCESS'
                )
            
            return True, token, expires_at, user_profile, None
        except Exception as e:
            logger.error(f"Failed to store session in Redis: {e}")
            return False, None, None, None, "REDIS_ERROR"

    def login(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[int], Optional[str]]:
        """
        Authenticate user and create session.
        
        Args:
            username: Username
            password: Plain text password
        
        Returns:
            Tuple of (success, token, expires_at, error_code)
            - success: True if login succeeded
            - token: Session token (UUID) if successful
            - expires_at: Token expiration timestamp (Unix seconds) if successful
            - error_code: Error code if failed (INVALID_CREDENTIALS)
        """
        success, token, expires_at, _user_profile, error_code = self._authenticate_and_create_session(
            username,
            password,
        )
        return success, token, expires_at, error_code

    def login_with_profile(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[Dict[str, Any]], Optional[str]]:
        """
        Authenticate user and create session, returning the authenticated profile.

        Returns:
            Tuple of (success, token, expires_at, user_profile, error_code)
        """
        return self._authenticate_and_create_session(username, password)
    
    def validate_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate session token and retrieve user information.
        
        Args:
            token: Session token
        
        Returns:
            Tuple of (valid, session_data, error_code)
            - valid: True if token is valid
            - session_data: Dict with userId and globalRole if valid
            - error_code: Error code if invalid (INVALID_TOKEN)
        """
        if not token:
            return False, None, "INVALID_TOKEN"
        
        try:
            session_data = self.redis.get_session(token)
            
            if not session_data:
                logger.debug(f"Token validation failed: token not found")
                return False, None, "INVALID_TOKEN"
            
            # Extract userId and globalRole
            user_id = session_data.get('userId')
            global_role = session_data.get('globalRole')
            
            if not user_id or not global_role:
                logger.error(f"Invalid session data structure: {session_data}")
                return False, None, "INVALID_TOKEN"
            
            return True, {"userId": user_id, "globalRole": global_role}, None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False, None, "REDIS_ERROR"
    
    def logout(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Logout user by deleting session.
        
        Args:
            token: Session token
        
        Returns:
            Tuple of (success, error_code)
            - success: True if logout succeeded
            - error_code: Error code if failed
        """
        if not token:
            return False, "INVALID_TOKEN"
        
        try:
            deleted = self.redis.delete_session(token)
            
            if deleted:
                logger.info(f"User logged out: token={token}")
                return True, None
            else:
                logger.debug(f"Logout: token not found (may have already expired)")
                # Still return success - token is gone either way
                return True, None
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False, "REDIS_ERROR"
