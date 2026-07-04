"""
Utility functions for password hashing and verification.
"""
import bcrypt
from config import logger

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    """
    if not password:
        password = ""
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    """
    try:
        if not password or not hashed:
            return False
        pwd_bytes = password.encode('utf-8')
        if len(pwd_bytes) > 72:
            pwd_bytes = pwd_bytes[:72]
        return bcrypt.checkpw(pwd_bytes, hashed.encode('utf-8'))
    except Exception as e:
        logger.debug(f"Password verification error: {e}")
        return False

def is_hashed(password: str) -> bool:
    """
    Check if a string looks like a bcrypt hash.
    """
    if not password:
        return False
    return any(password.startswith(p) for p in ["$2b$", "$2a$", "$2y$"])
