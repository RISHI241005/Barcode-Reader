"""Unit tests for AuditRepository security audit logging (Part 6)."""

from unittest.mock import MagicMock
import pytest

from src.models import AuditLog
from src.audit_repository import AuditRepository


def test_audit_log_action_execution():
    """Test 1: Recording an audit event executes parameterized SQL query with commit."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = AuditRepository(mock_db)
    ok = repo.log_action(
        action="USER_DEACTIVATED",
        user_id=1,
        username="admin",
        description="Account deactivated by admin",
        target_type="User",
        target_id="24",
    )

    assert ok is True
    assert mock_cursor.execute.called
    assert mock_conn.commit.called


def test_audit_get_logs():
    """Test 2: Retrieving audit logs with pagination."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    mock_cursor.fetchone.return_value = {"total": 1}
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "user_id": 1,
            "username": "admin",
            "action": "USER_DEACTIVATED",
            "target_type": "User",
            "target_id": "24",
            "description": "Account deactivated by admin",
            "created_at": "2026-08-17 10:45:00",
        }
    ]

    repo = AuditRepository(mock_db)
    logs, total = repo.get_audit_logs(page=1, page_size=20)

    assert total == 1
    assert len(logs) == 1
    assert logs[0].action == "USER_DEACTIVATED"
    assert logs[0].username == "admin"
