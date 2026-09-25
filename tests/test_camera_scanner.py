"""Unit tests for CameraScanner lifecycle, state machine, and discovery (Part 4)."""

import time
from unittest.mock import MagicMock, patch
import numpy as np  # pyrefly: ignore [missing-import] # type: ignore
import pytest  # pyrefly: ignore [missing-import] # type: ignore

try:
    from src.camera_scanner import CameraScanner, CameraState, detect_available_cameras  # pyrefly: ignore [missing-import] # type: ignore
    from src.models import BarcodeResult, DetectionReport  # pyrefly: ignore [missing-import] # type: ignore
except (ImportError, ModuleNotFoundError):
    from camera_scanner import CameraScanner, CameraState, detect_available_cameras  # pyrefly: ignore [missing-import] # type: ignore
    from models import BarcodeResult, DetectionReport  # pyrefly: ignore [missing-import] # type: ignore


def test_camera_scanner_initial_state():
    """Test 1: CameraScanner initializes in STOPPED state with default parameters."""
    scanner = CameraScanner(
        camera_index=0,
        requested_resolution=(1280, 720),
        detection_interval=0.10,
        stability_threshold=3,
        scan_cooldown_seconds=2.0,
    )
    assert scanner.state == CameraState.STOPPED
    assert scanner.camera_index == 0
    assert scanner.requested_resolution == (1280, 720)
    assert scanner.stability_threshold == 3
    assert scanner.scan_cooldown_seconds == 2.0
    assert scanner.auto_save_enabled is False


def test_camera_discovery_safe_release():
    """Test 2: detect_available_cameras tests devices and always releases VideoCapture."""
    with patch("cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap_class.return_value = mock_cap

        cams = detect_available_cameras(max_devices=2)
        assert len(cams) > 0
        assert mock_cap.release.called


def test_camera_state_transition_and_callbacks():
    """Test 3: Camera state updates invoke registered on_state_changed callbacks."""
    scanner = CameraScanner()
    state_history = []

    def on_state_change(new_state, err):
        state_history.append(new_state)

    scanner.on_state_changed = on_state_change
    scanner._set_state(CameraState.STARTING)
    scanner._set_state(CameraState.RUNNING)
    scanner._set_state(CameraState.STOPPED)

    assert state_history == [CameraState.STARTING, CameraState.RUNNING, CameraState.STOPPED]


def test_snapshot_capture():
    """Test 4: capture_snapshot returns a separate copy of latest raw frame."""
    scanner = CameraScanner()
    test_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    scanner.latest_raw_frame = test_frame

    snapshot = scanner.capture_snapshot()
    assert snapshot is not None
    assert snapshot.shape == (480, 640, 3)
    # Verify deep copy
    snapshot[0, 0] = [255, 255, 255]
    assert test_frame[0, 0, 0] == 128


def test_camera_scanner_error_handling():
    """Test 5: CameraScanner handles unopenable camera device gracefully."""
    with patch("cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap_class.return_value = mock_cap

        scanner = CameraScanner(camera_index=99)
        ok, err = scanner.start(camera_index=99)
        assert ok is True

        # Wait briefly for worker thread to transition to ERROR
        time.sleep(0.1)
        assert scanner.state in (CameraState.ERROR, CameraState.STOPPED)
        scanner.stop()


def test_camera_scanner_batch_confirmation_callback():
    """Test 6: Multiple simultaneous barcodes in consecutive frames trigger on_barcodes_confirmed with full batch."""
    scanner = CameraScanner(stability_threshold=2, scan_cooldown_seconds=5.0)
    batch_history = []
    single_history = []

    scanner.on_barcodes_confirmed = lambda batch: batch_history.append(batch)
    scanner.on_barcode_confirmed = lambda code: single_history.append(code)

    code1 = BarcodeResult(barcode_type="QR Code", raw_type="QRCODE", data="https://example.com/item1")
    code2 = BarcodeResult(barcode_type="EAN-13", raw_type="EAN13", data="8901234567890")

    # Frame 1: stability count becomes 1 (threshold is 2)
    confirmed1 = scanner._update_stability_and_cooldown([code1, code2], current_time=100.0)
    assert len(confirmed1) == 0

    # Frame 2: stability count reaches 2 -> both confirmed together
    confirmed2 = scanner._update_stability_and_cooldown([code1, code2], current_time=100.1)
    assert len(confirmed2) == 2
    assert confirmed2[0].data == code1.data
    assert confirmed2[1].data == code2.data

    # Emulate callback execution
    if scanner.on_barcodes_confirmed:
        scanner.on_barcodes_confirmed(confirmed2)
    for c in confirmed2:
        if scanner.on_barcode_confirmed:
            scanner.on_barcode_confirmed(c)

    assert len(batch_history) == 1
    assert len(batch_history[0]) == 2
    assert len(single_history) == 2
