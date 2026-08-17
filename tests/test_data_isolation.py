"""Unit tests for user-level data isolation and cross-user authorization enforcement (Part 6)."""

from unittest.mock import MagicMock
import pytest

from src.models import User, ScanRecord
from src.scan_repository import ScanRepository


def test_user_data_isolation_in_scan_queries():
    """Test 1: User A sees only User A's scans; User B sees only User B's scans."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)

    # 1. Query as User A (ID = 101)
    user_a = User(id=101, username="user_a", email="a@example.com", password_hash="h", role="USER")
    mock_cursor.fetchone.return_value = {"total": 1}
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "barcode_type": "EAN-13",
            "barcode_data": "8901234567890",
            "image_name": "scan_a.png",
            "scan_date": "2026-08-17 10:00:00",
            "validation_status": "Valid",
            "x_position": 0,
            "y_position": 0,
            "width": 100,
            "height": 50,
            "processing_method": "Original",
            "processing_time_ms": 10.0,
            "source": "image",
            "user_id": 101,
            "username": "user_a",
        }
    ]

    scans_a, total_a = repo.get_scans(user_id=user_a.id)
    assert total_a == 1
    assert scans_a[0].user_id == 101
    assert scans_a[0].barcode_data == "8901234567890"

    # Verify SQL query included user_id parameter for User A
    executed_params = mock_cursor.execute.call_args[0][1]
    assert 101 in executed_params

    # 2. Query as User B (ID = 102)
    user_b = User(id=102, username="user_b", email="b@example.com", password_hash="h", role="USER")
    mock_cursor.fetchall.return_value = [
        {
            "id": 2,
            "barcode_type": "QR Code",
            "barcode_data": "https://example.com/b",
            "image_name": "scan_b.png",
            "scan_date": "2026-08-17 11:00:00",
            "validation_status": "Not Available",
            "x_position": 0,
            "y_position": 0,
            "width": 100,
            "height": 100,
            "processing_method": "Original",
            "processing_time_ms": 12.0,
            "source": "camera",
            "user_id": 102,
            "username": "user_b",
        }
    ]

    scans_b, total_b = repo.get_scans(user_id=user_b.id)
    assert total_b == 1
    assert scans_b[0].user_id == 102
    assert scans_b[0].barcode_data == "https://example.com/b"

    executed_params_b = mock_cursor.execute.call_args[0][1]
    assert 102 in executed_params_b


def test_user_cannot_delete_another_users_scan():
    """Test 2: Normal User A cannot delete Scan B owned by User B."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)

    user_a = User(id=101, username="user_a", email="a@example.com", password_hash="h", role="USER")

    # When query runs `DELETE WHERE id = 2 AND user_id = 101`, rowcount is 0 because Scan #2 belongs to user 102
    mock_cursor.rowcount = 0

    ok, err = repo.delete_scan(scan_id=2, current_user=user_a)
    assert ok is False
    assert "unauthorized" in err.lower() or "not found" in err.lower()
    assert mock_conn.rollback.called


def test_admin_can_delete_any_scan():
    """Test 3: Admin can delete any scan regardless of owner."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)

    admin_user = User(id=1, username="admin", email="admin@example.com", password_hash="h", role="ADMIN")
    mock_cursor.rowcount = 1

    ok, err = repo.delete_scan(scan_id=2, current_user=admin_user)
    assert ok is True
    assert err is None
    # Admin deletion executes unconstrained by user_id
    mock_cursor.execute.assert_called_with("DELETE FROM barcode_scans WHERE id = %s;", (2,))
    assert mock_conn.commit.called
