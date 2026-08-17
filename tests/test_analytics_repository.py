"""Unit tests for AnalyticsRepository SQL aggregation and metrics calculation (Part 5)."""

from unittest.mock import MagicMock
import pytest

from src.analytics_repository import AnalyticsRepository


def test_analytics_summary_metrics():
    """Test 1: AnalyticsRepository properly fetches and computes summary KPIs."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # 1. Total & unique scans, today scans, cached products, user counts
    mock_cursor.fetchone.side_effect = [
        {"total_scans": 120, "unique_barcodes": 45},
        {"today_count": 14},
        {"prod_count": 30},
        {"total_users": 15, "active_users": 14},
    ]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = AnalyticsRepository(mock_db)
    summary = repo.get_summary_metrics(date_range="Last 7 Days")

    assert summary["total_scans"] == 120
    assert summary["unique_barcodes"] == 45
    assert summary["today_scans"] == 14
    assert summary["total_products"] == 30
    assert summary["lookup_rate"] == 66.7


def test_analytics_type_distribution():
    """Test 2: Barcode type distribution query execution."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("EAN-13", 80), ("QR Code", 30), ("Code 128", 10)]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = AnalyticsRepository(mock_db)
    dist = repo.get_barcode_type_distribution(date_range="All Time", limit=5)

    assert len(dist) == 3
    assert dist[0] == ("EAN-13", 80)
    assert dist[1] == ("QR Code", 30)


def test_analytics_source_distribution():
    """Test 3: Scan source distribution aggregation (Camera vs Image)."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("camera", 70), ("image", 50)]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = AnalyticsRepository(mock_db)
    sources = repo.get_source_distribution()

    assert sources["camera"] == 70
    assert sources["image"] == 50


def test_analytics_daily_counts():
    """Test 4: Daily scan count query."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("08-15", 12), ("08-16", 18), ("08-17", 25)]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = AnalyticsRepository(mock_db)
    daily = repo.get_daily_scan_counts(days=7)

    assert len(daily) == 3
    assert daily[2] == ("08-17", 25)
