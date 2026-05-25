"""Password hashing utilities using bcrypt.

BUGFIX C10: bcrypt only considers the first 72 bytes of input. To avoid
silent truncation (where two long passwords differing only after byte 72
would collide), we pre-hash with SHA-256 and base64-encode the digest
before feeding into bcrypt. The pre-hash produces a fixed-size 44-byte
base64 string that fits comfortably under bcrypt's 72-byte window.

This is a well-known mitigation (used by Dropbox and others). The salt
and cost-factor protection of bcrypt are preserved.
"""
import base64
import hashlib
import bcrypt
from logging_config import get_logger

logger = get_logger(__name__)


def _prehash(password: str) -> bytes:
    """SHA-256 + base64 the password to bypass the 72-byte bcrypt truncation."""
    if not password:
        return b""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    # base64 of a 32-byte digest = 44 ASCII bytes — safely under bcrypt's
    # 72-byte input limit, and contains no NUL bytes.
    return base64.b64encode(digest)


class PasswordHasher:
    """Password hashing and verification using bcrypt with cost factor 12.

    Each password is pre-hashed with SHA-256 + base64 to avoid bcrypt's
    72-byte truncation. See module docstring for rationale.
    """

    # Cost factor for bcrypt (2^12 iterations)
    COST_FACTOR = 12

    @staticmethod
    def hash(password: str) -> str:
        """Hash a password using bcrypt with cost factor 12 (SHA-256 pre-hashed)."""
        if not password:
            raise ValueError("Password cannot be empty")

        salt = bcrypt.gensalt(rounds=PasswordHasher.COST_FACTOR)
        pre = _prehash(password)
        hashed = bcrypt.hashpw(pre, salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify(password: str, password_hash: str) -> bool:
        """Verify a password against a bcrypt hash (SHA-256 pre-hashed)."""
        if not password or not password_hash:
            return False

        try:
            pre = _prehash(password)
            hash_bytes = password_hash.encode("utf-8")
            return bcrypt.checkpw(pre, hash_bytes)
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
