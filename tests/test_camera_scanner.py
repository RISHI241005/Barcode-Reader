"""Unit tests for CameraScanner lifecycle, state machine, and discovery (Part 4)."""

import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.camera_scanner import CameraScanner, CameraState, detect_available_cameras
from src.models import BarcodeResult, DetectionReport


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
