"""Unit tests for AuthService registration, login, rate limiting, and password change (Part 6)."""

from unittest.mock import MagicMock
import pytest

from src.models import User
from src.auth_service import AuthService
from src.security import hash_password


def test_auth_registration_success():
    """Test 1: Successful user registration hashes password and logs audit event."""
    mock_user_repo = MagicMock()
    mock_session_mgr = MagicMock()
    mock_audit_repo = MagicMock()

    mock_user_repo.create_user.return_value = (True, 10, None)

    auth = AuthService(user_repo=mock_user_repo, session_mgr=mock_session_mgr, audit_repo=mock_audit_repo)
    ok, user, err = auth.register(
        username="john_doe",
        email="john@example.com",
        password="secretpassword",
        confirm_password="secretpassword",
        role="USER",
    )

    assert ok is True
    assert user is not None
    assert user.id == 10
    assert user.role == "USER"
    assert mock_audit_repo.log_action.called


def test_auth_registration_password_mismatch():
    """Test 2: Registration rejects mismatched passwords."""
    mock_user_repo = MagicMock()
    auth = AuthService(user_repo=mock_user_repo)

    ok, user, err = auth.register(
        username="john_doe",
        email="john@example.com",
        password="secretpassword",
        confirm_password="differentpassword",
    )

    assert ok is False
    assert user is None
    assert "match" in err.lower()


def test_auth_login_success_with_username_or_email():
    """Test 3: Successful login with valid password initializes session."""
    mock_user_repo = MagicMock()
    mock_session_mgr = MagicMock()
    mock_audit_repo = MagicMock()

    test_user = User(
        id=1,
        username="rishi",
        email="rishi@example.com",
        password_hash=hash_password("ValidPassword123"),
        role="ADMIN",
        is_active=True,
    )
    mock_user_repo.get_user_by_username_or_email.return_value = test_user

    auth = AuthService(user_repo=mock_user_repo, session_mgr=mock_session_mgr, audit_repo=mock_audit_repo)

    # Login by username
    ok, u, err = auth.login("rishi", "ValidPassword123")
    assert ok is True
    assert u.username == "rishi"
    mock_session_mgr.create_session.assert_called_with(test_user)
    mock_user_repo.update_last_login.assert_called_with(1)

    # Login by email
    ok, u, err = auth.login("rishi@example.com", "ValidPassword123")
    assert ok is True
    assert u.email == "rishi@example.com"


def test_auth_login_invalid_credentials():
    """Test 4: Login with incorrect password returns generic error."""
    mock_user_repo = MagicMock()
    mock_session_mgr = MagicMock()
    mock_audit_repo = MagicMock()

    test_user = User(
        id=1,
        username="rishi",
        email="rishi@example.com",
        password_hash=hash_password("ValidPassword123"),
        role="ADMIN",
        is_active=True,
    )
    mock_user_repo.get_user_by_username_or_email.return_value = test_user

    auth = AuthService(user_repo=mock_user_repo, session_mgr=mock_session_mgr, audit_repo=mock_audit_repo)
    ok, u, err = auth.login("rishi", "WrongPassword")

    assert ok is False
    assert u is None
    assert "invalid username/email or password" in err.lower()
    assert not mock_session_mgr.create_session.called


def test_auth_login_deactivated_account():
    """Test 5: Login with deactivated account is blocked with clear message."""
    mock_user_repo = MagicMock()
    mock_session_mgr = MagicMock()

    deactivated_user = User(
        id=2,
        username="inactive_user",
        email="inactive@example.com",
        password_hash=hash_password("ValidPassword123"),
        role="USER",
        is_active=False,
    )
    mock_user_repo.get_user_by_username_or_email.return_value = deactivated_user

    auth = AuthService(user_repo=mock_user_repo, session_mgr=mock_session_mgr)
    ok, u, err = auth.login("inactive_user", "ValidPassword123")

    assert ok is False
    assert "inactive" in err.lower()


def test_auth_change_password():
    """Test 6: User password change verifies current password and updates hash."""
    mock_user_repo = MagicMock()
    mock_user_repo.update_password.return_value = (True, None)

    user = User(
        id=5,
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("OldPassword123"),
    )
    mock_user_repo.get_user_by_id.return_value = user

    auth = AuthService(user_repo=mock_user_repo)

    # Incorrect current password
    ok, err = auth.change_password(5, "WrongOldPassword", "NewPassword123", "NewPassword123")
    assert ok is False
    assert "current password is incorrect" in err.lower()

    # Correct current password
    ok, err = auth.change_password(5, "OldPassword123", "NewPassword123", "NewPassword123")
    assert ok is True
    assert err is None
    assert mock_user_repo.update_password.called
