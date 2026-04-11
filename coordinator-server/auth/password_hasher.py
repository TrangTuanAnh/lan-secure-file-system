"""Password hashing utilities using bcrypt."""
import bcrypt
from logging_config import get_logger

logger = get_logger(__name__)


class PasswordHasher:
    """Password hashing and verification using bcrypt with cost factor 12."""
    
    # Cost factor for bcrypt (2^12 iterations)
    COST_FACTOR = 12
    
    @staticmethod
    def hash(password: str) -> str:
        """
        Hash a password using bcrypt with cost factor 12.
        
        Args:
            password: Plain text password
        
        Returns:
            Bcrypt hash string (includes salt)
        
        Raises:
            ValueError: If password is empty
        """
        if not password:
            raise ValueError("Password cannot be empty")
        
        # Generate salt and hash password
        salt = bcrypt.gensalt(rounds=PasswordHasher.COST_FACTOR)
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        # Return as string (bcrypt returns bytes)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify(password: str, password_hash: str) -> bool:
        """
        Verify a password against a bcrypt hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Bcrypt hash to check against
        
        Returns:
            True if password matches hash, False otherwise
        """
        if not password or not password_hash:
            return False
        
        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
