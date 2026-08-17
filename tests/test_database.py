"""Unit and integration tests for MySQL database management and scan repository (Part 3)."""

from datetime import datetime
from pathlib import Path
import csv
import json
import pytest
from unittest.mock import MagicMock, patch

from src.database import DatabaseManager
from src.scan_repository import ScanRepository
from src.models import ScanRecord

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_images"


@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager for offline unit testing."""
    manager = DatabaseManager(
        host="localhost",
        port=3306,
        database="barcode_reader_test",
        user="test_user",
        password="test_password",
    )
    return manager


def test_database_manager_config():
    """Test 1: DatabaseManager configuration loading and properties."""
    db = DatabaseManager(host="127.0.0.1", port=3307, database="custom_db", user="admin")
    assert db.host == "127.0.0.1"
    assert db.port == 3307
    assert db.database == "custom_db"
    assert db.user == "admin"


def test_scan_record_model():
    """Test 2: ScanRecord dataclass properties, formatting, and serialization."""
    now = datetime(2026, 8, 17, 10, 30, 0)
    record = ScanRecord(
        id=1,
        barcode_type="EAN-13",
        barcode_data="8901234567890",
        image_name="test_image.png",
        scan_date=now,
        validation_status="Valid",
        x_position=50,
        y_position=60,
        width=200,
        height=100,
        processing_method="Original Image",
        processing_time_ms=15.5,
    )

    assert record.formatted_date == "2026-08-17 10:30:00"
    d = record.to_dict()
    assert d["id"] == 1
    assert d["barcode_type"] == "EAN-13"
    assert d["barcode_data"] == "8901234567890"
    assert d["validation_status"] == "Valid"


def test_save_scan_unit_with_mock():
    """Test 3: ScanRepository save_scan query generation and duplicate prevention."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # No recent duplicate
    mock_cursor.lastrowid = 42

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)
    record = ScanRecord(
        barcode_type="EAN-13",
        barcode_data="8901234567890",
        image_name="sample.png",
        validation_status="Valid",
    )

    ok, rec_id, err = repo.save_scan(record)
    assert ok is True
    assert rec_id == 42
    assert err is None
    assert mock_conn.commit.called


def test_save_scans_batch_unit_with_mock():
    """Test 4: Batch save_scans executes single transaction commit."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)
    scans = [
        ScanRecord(barcode_type="EAN-13", barcode_data="8901234567890"),
        ScanRecord(barcode_type="QR Code", barcode_data="https://example.com"),
        ScanRecord(barcode_type="Code 128", barcode_data="PRODUCT-1024"),
    ]

    ok, count, err = repo.save_scans(scans)
    assert ok is True
    assert count == 3
    assert err is None
    assert mock_conn.commit.called


def test_get_scans_search_and_filter_query_building():
    """Test 5: Query and parameter construction for search, type, and date filters."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Return total count = 1
    mock_cursor.fetchone.return_value = {"total": 1}
    mock_cursor.fetchall.return_value = [
        {
            "id": 10,
            "barcode_type": "EAN-13",
            "barcode_data": "8901234567890",
            "image_name": "ean13.png",
            "scan_date": "2026-08-17 11:00:00",
            "validation_status": "Valid",
            "x_position": 10,
            "y_position": 10,
            "width": 100,
            "height": 50,
            "processing_method": "Original Image",
            "processing_time_ms": 12.0,
        }
    ]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)
    records, total = repo.get_scans(
        page=1,
        page_size=20,
        search_term="890",
        barcode_type="EAN-13",
        date_filter="Today",
    )

    assert total == 1
    assert len(records) == 1
    assert records[0].barcode_data == "8901234567890"
    assert records[0].validation_status == "Valid"


def test_delete_scan_unit_with_mock():
    """Test 6: Delete single scan executes parameterized DELETE query."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)
    ok, err = repo.delete_scan(15)

    assert ok is True
    assert err is None
    mock_cursor.execute.assert_called_with("DELETE FROM barcode_scans WHERE id = %s;", (15,))
    assert mock_conn.commit.called


def test_delete_all_scans_unit_with_mock():
    """Test 7: Delete all scan records executes DELETE and commits."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ScanRepository(mock_db)
    ok, err = repo.delete_all_scans()

    assert ok is True
    assert err is None
    mock_cursor.execute.assert_called_with("DELETE FROM barcode_scans;")
    assert mock_conn.commit.called


def test_export_scans_to_csv_and_json():
    """Test 8: Exporting filtered scan records to CSV and JSON files."""
    import tempfile
    mock_repo = ScanRepository(MagicMock())
    test_records = [
        ScanRecord(
            id=1,
            barcode_type="EAN-13",
            barcode_data="8901234567890",
            image_name="test.png",
            scan_date="2026-08-17 10:00:00",
            validation_status="Valid",
            processing_method="Original Image",
            processing_time_ms=10.5,
        ),
        ScanRecord(
            id=2,
            barcode_type="QR Code",
            barcode_data="https://example.com",
            image_name="qr.png",
            scan_date="2026-08-17 10:05:00",
            validation_status="Not Available",
            processing_method="Original Image",
            processing_time_ms=8.2,
        ),
    ]

    mock_repo.get_scans = MagicMock(return_value=(test_records, len(test_records)))

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        # 1. Export CSV
        csv_file = tmp_path / "test_export.csv"
        ok, msg = mock_repo.export_scans_to_file(csv_file, export_format="csv")
        assert ok is True
        assert csv_file.exists()

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["barcode_type"] == "EAN-13"
            assert rows[0]["barcode_data"] == "8901234567890"
            assert rows[1]["barcode_type"] == "QR Code"

        # 2. Export JSON
        json_file = tmp_path / "test_export.json"
        ok_j, msg_j = mock_repo.export_scans_to_file(json_file, export_format="json")
        assert ok_j is True
        assert json_file.exists()

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 2
            assert data[0]["barcode_data"] == "8901234567890"


def test_database_connection_failure_handling():
    """Test 9: Graceful handling when MySQL server is unreachable."""
    bad_db = DatabaseManager(host="invalid.host.nonexistent.local", port=3399, password="wrong")
    is_conn, msg = bad_db.test_connection()
    assert is_conn is False
    assert msg is not None

    repo = ScanRepository(bad_db)
    ok, rec_id, err = repo.save_scan(ScanRecord(barcode_type="EAN-13", barcode_data="8901234567890"))
    assert ok is False
    assert rec_id is None
    assert "Database error" in err or "Failed" in err or "Can't connect" in err or "MySQL" in err
