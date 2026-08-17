"""Unit tests for SessionManager and inactivity timeout handling (Part 6)."""

import time
import pytest

from src.models import User
from src.session_manager import SessionManager


def test_session_creation_and_properties():
    """Test 1: Creating a session stores identity without storing passwords."""
    user = User(id=1, username="rishi", email="rishi@example.com", password_hash="secret_hash", role="ADMIN")
    mgr = SessionManager(timeout_minutes=30)

    assert mgr.is_authenticated() is False
    mgr.create_session(user)

    assert mgr.is_authenticated() is True
    assert mgr.user_id == 1
    assert mgr.username == "rishi"
    assert mgr.is_admin is True


def test_session_inactivity_timeout():
    """Test 2: Inactivity beyond configured timeout expires the session."""
    user = User(id=2, username="bob", email="bob@example.com", password_hash="secret_hash", role="USER")
    mgr = SessionManager(timeout_minutes=1)  # 60s
    mgr.create_session(user)

    assert mgr.is_expired() is False

    # Simulate elapsed time of 65 seconds
    mgr.last_activity_time = time.time() - 65
    assert mgr.is_expired() is True
    assert mgr.is_authenticated() is False  # Clearing on expiration


def test_session_touch_extends_activity():
    """Test 3: touch() updates last activity timestamp."""
    user = User(id=3, username="carol", email="carol@example.com", password_hash="h", role="USER")
    mgr = SessionManager(timeout_minutes=1)
    mgr.create_session(user)

    mgr.last_activity_time = time.time() - 40
    mgr.touch()
    assert (time.time() - mgr.last_activity_time) < 1.0


def test_session_clear():
    """Test 4: clear_session resets all state."""
    user = User(id=4, username="dan", email="dan@example.com", password_hash="h", role="USER")
    mgr = SessionManager(timeout_minutes=30)
    mgr.create_session(user)

    mgr.clear_session()
    assert mgr.is_authenticated() is False
    assert mgr.current_user is None
    assert mgr.user_id is None
