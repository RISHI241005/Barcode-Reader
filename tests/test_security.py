"""Unit tests for password hashing, input validation, and login rate limiting (Part 6)."""

import time
import pytest

from src.security import (
    hash_password,
    verify_password,
    validate_username,
    validate_email,
    validate_password,
    check_login_lockout,
    record_failed_login,
    record_successful_login,
)


def test_password_hashing_and_verification():
    """Test 1: Password hashing produces valid bcrypt hashes and verify matches correctly."""
    plain = "SuperSecret123!"
    hashed = hash_password(plain)

    assert hashed != plain
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_username_validation():
    """Test 2: Username format, length, and character validation."""
    assert validate_username("rishi")[0] is True
    assert validate_username("john_doe_99")[0] is True

    # Invalid cases
    assert validate_username("")[0] is False
    assert validate_username("ab")[0] is False  # too short (< 3)
    assert validate_username("user@name")[0] is False  # invalid char '@'
    assert validate_username("user name")[0] is False  # space not allowed


def test_email_validation():
    """Test 3: Email format validation."""
    assert validate_email("rishi@example.com")[0] is True
    assert validate_email("admin.sub@domain.co.uk")[0] is True

    # Invalid cases
    assert validate_email("")[0] is False
    assert validate_email("notanemail")[0] is False
    assert validate_email("user@")[0] is False
    assert validate_email("@domain.com")[0] is False


def test_password_validation():
    """Test 4: Password minimum length requirement."""
    assert validate_password("123456")[0] is True
    assert validate_password("StrongPassword#2026")[0] is True

    # Invalid cases
    assert validate_password("")[0] is False
    assert validate_password("12345")[0] is False  # < 6 chars


def test_login_rate_limiting_and_lockout():
    """Test 5: Failed login rate-limiting locks account temporarily after max attempts."""
    test_user = "test_lockout_user"
    record_successful_login(test_user)  # Reset

    # 4 failed attempts should not trigger lockout yet
    for _ in range(4):
        record_failed_login(test_user)
        is_locked, _ = check_login_lockout(test_user)
        assert is_locked is False

    # 5th failed attempt triggers lockout
    record_failed_login(test_user)
    is_locked, msg = check_login_lockout(test_user)
    assert is_locked is True
    assert "too many failed" in msg.lower()

    # Successful login resets the counter
    record_successful_login(test_user)
    is_locked, _ = check_login_lockout(test_user)
    assert is_locked is False
