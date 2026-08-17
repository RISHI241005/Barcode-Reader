"""Security utilities for password hashing, verification, input validation, and rate limiting (Part 6)."""

import os
import re
import time
from typing import Dict, Optional, Tuple
import bcrypt

from src.utils import get_logger

logger = get_logger()

# Security configuration defaults
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "5"))
LOGIN_LOCKOUT_SECONDS = LOGIN_LOCKOUT_MINUTES * 60

# In-memory rate limiting tracking: identifier -> (failed_count, lockout_expiry_time)
_failed_attempts: Dict[str, Tuple[int, float]] = {}


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password securely using bcrypt with automatic salt generation."""
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    salt = bcrypt.gensalt(rounds=12)
    hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """Validate username requirements: 3-50 alphanumeric or underscore characters."""
    if not username or not username.strip():
        return False, "Username is required."
    u = username.strip()
    if len(u) < 3:
        return False, "Username must be at least 3 characters long."
    if len(u) > 50:
        return False, "Username cannot exceed 50 characters."
    if not re.match(r"^[a-zA-Z0-9_]+$", u):
        return False, "Username can only contain letters, numbers, and underscores (_)."
    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate email format with standard regular expression pattern."""
    if not email or not email.strip():
        return False, "Email address is required."
    e = email.strip()
    if len(e) > 255:
        return False, "Email cannot exceed 255 characters."
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, e):
        return False, "Please enter a valid email address."
    return True, None


def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """Validate password strength requirements (minimum 6 characters)."""
    if not password:
        return False, "Password is required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    return True, None


def check_login_lockout(identifier: str) -> Tuple[bool, Optional[str]]:
    """Check if a given username/email is currently locked out due to repeated failed logins."""
    ident = identifier.strip().lower()
    if ident not in _failed_attempts:
        return False, None

    failed_count, lockout_expiry = _failed_attempts[ident]
    now = time.time()

    if lockout_expiry > now:
        remaining_secs = int(lockout_expiry - now)
        remaining_mins = max(1, (remaining_secs + 59) // 60)
        return (
            True,
            f"Too many failed login attempts. Please try again in {remaining_mins} minute(s).",
        )

    if now >= lockout_expiry and lockout_expiry > 0:
        # Lockout expired, reset attempt counter
        _failed_attempts.pop(ident, None)

    return False, None


def record_failed_login(identifier: str):
    """Increment failed login attempts counter and apply lockout if threshold exceeded."""
    ident = identifier.strip().lower()
    failed_count, _ = _failed_attempts.get(ident, (0, 0.0))
    failed_count += 1

    if failed_count >= MAX_LOGIN_ATTEMPTS:
        lockout_expiry = time.time() + LOGIN_LOCKOUT_SECONDS
        _failed_attempts[ident] = (failed_count, lockout_expiry)
        logger.warning(
            f"Account identifier `{ident}` locked out for {LOGIN_LOCKOUT_MINUTES} minutes "
            f"after {failed_count} failed login attempts."
        )
    else:
        _failed_attempts[ident] = (failed_count, 0.0)
        logger.info(f"Failed login attempt {failed_count}/{MAX_LOGIN_ATTEMPTS} for `{ident}`.")


def record_successful_login(identifier: str):
    """Clear failed login attempts counter on successful authentication."""
    ident = identifier.strip().lower()
    _failed_attempts.pop(ident, None)
