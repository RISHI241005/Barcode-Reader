"""Unit tests for UserRepository and Last-Admin protection rules (Part 6)."""

from unittest.mock import MagicMock
import pytest

from src.models import User
from src.user_repository import UserRepository


def test_user_repository_create_and_get():
    """Test 1: UserRepository creates user and fetches by username/email."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate username/email check (returns None = no duplicate)
    mock_cursor.fetchone.return_value = None
    mock_cursor.lastrowid = 1

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = UserRepository(mock_db)
    u = User(username="newuser", email="new@example.com", password_hash="hash123")

    ok, uid, err = repo.create_user(u)
    assert ok is True
    assert uid == 1
    assert mock_conn.commit.called


def test_last_admin_deactivation_protection():
    """Test 2: System rejects deactivation of the last active administrator."""
    mock_db = MagicMock()
    repo = UserRepository(mock_db)

    admin_user = User(id=1, username="admin1", email="admin1@example.com", password_hash="h", role="ADMIN", is_active=True)
    repo.get_user_by_id = MagicMock(return_value=admin_user)
    repo.count_active_admins = MagicMock(return_value=1)  # Only 1 admin!

    ok, err = repo.set_user_active_status(1, is_active=False)
    assert ok is False
    assert "cannot deactivate the last active administrator" in err.lower()


def test_last_admin_role_demotion_protection():
    """Test 3: System rejects demoting the last active administrator to USER."""
    mock_db = MagicMock()
    repo = UserRepository(mock_db)

    admin_user = User(id=1, username="admin1", email="admin1@example.com", password_hash="h", role="ADMIN", is_active=True)
    repo.get_user_by_id = MagicMock(return_value=admin_user)
    repo.count_active_admins = MagicMock(return_value=1)

    ok, err = repo.set_user_role(1, "USER")
    assert ok is False
    assert "cannot remove the last active administrator" in err.lower()


def test_admin_deactivation_allowed_when_multiple_admins():
    """Test 4: When 2 active admins exist, deactivating one is allowed."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = UserRepository(mock_db)

    admin_user = User(id=1, username="admin1", email="admin1@example.com", password_hash="h", role="ADMIN", is_active=True)
    repo.get_user_by_id = MagicMock(return_value=admin_user)
    repo.count_active_admins = MagicMock(return_value=2)  # 2 admins exist!

    ok, err = repo.set_user_active_status(1, is_active=False)
    assert ok is True
    assert err is None
    assert mock_conn.commit.called
