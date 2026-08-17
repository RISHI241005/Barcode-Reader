"""Unit tests for barcode stability detection, consecutive frame tracking, and duplicate cooldown (Part 4)."""

import time
import pytest

from src.camera_scanner import CameraScanner
from src.models import BarcodeResult


def test_consecutive_detection_stability_threshold():
    """Test 1: Barcode is only confirmed once stability threshold (e.g. 3 frames) is reached."""
    scanner = CameraScanner(stability_threshold=3, scan_cooldown_seconds=2.0)
    barcode = BarcodeResult(barcode_type="EAN-13", raw_type="EAN_13", data="8901234567890")

    t0 = 1000.0

    # Frame 1: count = 1 -> not confirmed
    confirmed_1 = scanner._update_stability_and_cooldown([barcode], current_time=t0)
    assert len(confirmed_1) == 0

    # Frame 2: count = 2 -> not confirmed
    confirmed_2 = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 0.1)
    assert len(confirmed_2) == 0

    # Frame 3: count = 3 -> CONFIRMED!
    confirmed_3 = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 0.2)
    assert len(confirmed_3) == 1
    assert confirmed_3[0].data == "8901234567890"


def test_duplicate_cooldown_prevention():
    """Test 2: Once confirmed, continuous detections within cooldown period are not re-confirmed."""
    scanner = CameraScanner(stability_threshold=3, scan_cooldown_seconds=2.0)
    barcode = BarcodeResult(barcode_type="EAN-13", raw_type="EAN_13", data="8901234567890")

    t0 = 1000.0

    # Reach threshold (3 frames)
    scanner._update_stability_and_cooldown([barcode], current_time=t0)
    scanner._update_stability_and_cooldown([barcode], current_time=t0 + 0.1)
    confirmed = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 0.2)
    assert len(confirmed) == 1

    # Frame 4 (at t0 + 0.5s): within 2.0s cooldown -> MUST NOT CONFIRM AGAIN
    confirmed_again = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 0.5)
    assert len(confirmed_again) == 0

    # Frame 5 (at t0 + 1.5s): still within cooldown -> MUST NOT CONFIRM AGAIN
    confirmed_again_2 = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 1.5)
    assert len(confirmed_again_2) == 0

    # Frame 6 (at t0 + 2.5s): cooldown expired -> CAN CONFIRM AGAIN!
    confirmed_after_cooldown = scanner._update_stability_and_cooldown([barcode], current_time=t0 + 2.5)
    assert len(confirmed_after_cooldown) == 1
    assert confirmed_after_cooldown[0].data == "8901234567890"


def test_disappearing_barcode_resets_consecutive_count():
    """Test 3: Barcode disappearing from frame resets its consecutive counter."""
    scanner = CameraScanner(stability_threshold=3, scan_cooldown_seconds=2.0)
    b1 = BarcodeResult(barcode_type="EAN-13", raw_type="EAN_13", data="8901234567890")

    t0 = 1000.0
    # Seen 2 times (threshold is 3)
    scanner._update_stability_and_cooldown([b1], current_time=t0)
    scanner._update_stability_and_cooldown([b1], current_time=t0 + 0.1)

    # Frame with NO barcodes (disappeared)
    scanner._update_stability_and_cooldown([], current_time=t0 + 0.2)
    assert ("EAN-13", "8901234567890") not in scanner._consecutive_counts

    # Appears again -> count restarts at 1, so 1st frame shouldn't confirm
    conf = scanner._update_stability_and_cooldown([b1], current_time=t0 + 0.3)
    assert len(conf) == 0


def test_multiple_concurrent_barcodes_stability():
    """Test 4: Multiple barcodes detected in the same frame track stability independently."""
    scanner = CameraScanner(stability_threshold=2, scan_cooldown_seconds=2.0)
    b1 = BarcodeResult(barcode_type="EAN-13", raw_type="EAN_13", data="8901234567890")
    b2 = BarcodeResult(barcode_type="QR Code", raw_type="QR_CODE", data="https://example.com")

    t0 = 1000.0
    # Frame 1: both seen once
    scanner._update_stability_and_cooldown([b1, b2], current_time=t0)

    # Frame 2: both reach threshold (2) -> both confirmed
    conf = scanner._update_stability_and_cooldown([b1, b2], current_time=t0 + 0.1)
    assert len(conf) == 2
    datas = {c.data for c in conf}
    assert "8901234567890" in datas
    assert "https://example.com" in datas
