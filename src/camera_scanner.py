"""Real-time camera scanner module for Barcode Reader (Part 4).

Handles camera discovery, asynchronous frame capture, configurable detection frequency,
barcode stability tracking, scan cooldown, bounding box rendering, and safe resource release.
"""

from enum import Enum
import os
from pathlib import Path
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.barcode_detector import BarcodeDetector
from src.image_processor import ImageProcessor
from src.models import BarcodeResult, DetectionReport
from src.utils import get_logger

logger = get_logger()


class CameraState(str, Enum):
    """Lifecycle state of the camera scanner."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


def detect_available_cameras(max_devices: int = 4) -> List[int]:
    """Scan and return a list of available camera device indices.
    
    Tests device indices from 0 to max_devices-1 and safely releases them immediately.
    """
    available_indices = []
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY

    for index in range(max_devices):
        cap = None
        try:
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available_indices.append(index)
        except Exception as e:
            logger.debug(f"Camera index {index} test failed: {e}")
        finally:
            if cap is not None:
                cap.release()

    logger.info(f"Available cameras detected: {available_indices if available_indices else '[None (will use default 0)]'}")
    return available_indices if available_indices else [0]


class CameraScanner:
    """Manages real-time webcam capture, decoding thread, stability detection, and frame rendering."""

    def __init__(
        self,
        detector: Optional[BarcodeDetector] = None,
        camera_index: int = 0,
        requested_resolution: Tuple[int, int] = (1280, 720),
        detection_interval: float = 0.10,
        stability_threshold: int = 3,
        scan_cooldown_seconds: float = 2.0,
    ):
        self.detector = detector or BarcodeDetector()
        self.camera_index = camera_index
        self.requested_resolution = requested_resolution
        self.actual_resolution: Tuple[int, int] = (0, 0)
        self.detection_interval = detection_interval
        self.stability_threshold = stability_threshold
        self.scan_cooldown_seconds = scan_cooldown_seconds
        self.auto_save_enabled = False

        # State management
        self.state = CameraState.STOPPED
        self.error_message: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Bounded frame storage (never unbounded lists)
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_display_frame: Optional[np.ndarray] = None
        self.latest_report: Optional[DetectionReport] = None
        self.latest_results: List[BarcodeResult] = []

        # Stability & duplicate cooldown tracking
        # key: (barcode_type, barcode_data) -> count of consecutive detections
        self._consecutive_counts: Dict[Tuple[str, str], int] = {}
        # key: (barcode_type, barcode_data) -> last confirmed timestamp
        self._last_confirmed_timestamps: Dict[Tuple[str, str], float] = {}

        # Performance metrics
        self.fps: float = 0.0
        self._frame_count = 0
        self._fps_start_time = time.time()

        # Callbacks
        self.on_frame_ready: Optional[Callable[[np.ndarray, List[BarcodeResult]], None]] = None
        self.on_barcode_confirmed: Optional[Callable[[BarcodeResult], None]] = None
        self.on_state_changed: Optional[Callable[[CameraState, Optional[str]], None]] = None

    def _set_state(self, new_state: CameraState, error: Optional[str] = None):
        """Update scanner state and notify registered listeners."""
        self.state = new_state
        self.error_message = error
        if self.on_state_changed:
            try:
                self.on_state_changed(new_state, error)
            except Exception as e:
                logger.error(f"Error in on_state_changed callback: {e}")

    def start(self, camera_index: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """Start the background camera frame acquisition and detection loop."""
        with self._lock:
            if self.state in (CameraState.RUNNING, CameraState.STARTING):
                return True, "Camera is already active."

            if camera_index is not None:
                self.camera_index = camera_index

            self._set_state(CameraState.STARTING)
            self._stop_event.clear()
            self._consecutive_counts.clear()

            # Start worker thread
            self._thread = threading.Thread(target=self._capture_worker, daemon=True)
            self._thread.start()
            return True, None

    def stop(self):
        """Stop camera capture and release webcam resources safely."""
        with self._lock:
            if self.state == CameraState.STOPPED:
                return

            self._set_state(CameraState.STOPPING)
            self._stop_event.set()

        # Wait for thread to finish cleanly without blocking UI permanently
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self._set_state(CameraState.STOPPED)
            self.latest_raw_frame = None
            self.latest_display_frame = None
            self.latest_results.clear()
            self._consecutive_counts.clear()
            logger.info("Camera scanner stopped and resources released.")

    def switch_camera(self, new_index: int) -> Tuple[bool, Optional[str]]:
        """Switch to another camera index."""
        self.stop()
        return self.start(new_index)

    def capture_snapshot(self) -> Optional[np.ndarray]:
        """Return a copy of the current raw camera frame for freezing/saving."""
        with self._lock:
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
        return None

    def _capture_worker(self):
        """Background thread worker for capturing frames and running barcode detection."""
        cap = None
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY

        try:
            logger.info(f"Opening camera index {self.camera_index}...")
            cap = cv2.VideoCapture(self.camera_index, backend)

            if not cap.isOpened():
                # Fallback to standard CAP_ANY if DSHOW failed
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                err = f"Unable to access camera index {self.camera_index}. Device may be in use or disconnected."
                logger.error(err)
                self._set_state(CameraState.ERROR, err)
                return

            # Configure requested resolution
            req_w, req_h = self.requested_resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.actual_resolution = (actual_w, actual_h)
            logger.info(f"Camera {self.camera_index} active with resolution {actual_w}×{actual_h}")

            self._set_state(CameraState.RUNNING)

            last_detection_time = 0.0
            current_results: List[BarcodeResult] = []
            self._fps_start_time = time.time()
            self._frame_count = 0

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                self._frame_count += 1
                now = time.time()
                elapsed = now - self._fps_start_time
                if elapsed >= 1.0:
                    self.fps = round(self._frame_count / elapsed, 1)
                    self._frame_count = 0
                    self._fps_start_time = now

                # 1. Barcode Detection on configured interval
                if now - last_detection_time >= self.detection_interval:
                    last_detection_time = now
                    report = self.detector.detect_and_decode(frame, fast_mode=True)
                    self.latest_report = report
                    current_results = report.results if report.success else []

                    # Process stability and cooldown triggers
                    confirmed_barcodes = self._update_stability_and_cooldown(current_results, now)
                    for confirmed in confirmed_barcodes:
                        if self.on_barcode_confirmed:
                            try:
                                self.on_barcode_confirmed(confirmed)
                            except Exception as e:
                                logger.error(f"Error in on_barcode_confirmed callback: {e}")

                # 2. Render Live Bounding Boxes & Reticle Guide
                display_frame = frame.copy()
                if current_results:
                    display_frame = ImageProcessor.draw_bounding_boxes(
                        display_frame, current_results
                    )
                else:
                    # Draw subtle scanning reticle guide
                    self._draw_reticle_guide(display_frame)

                with self._lock:
                    self.latest_raw_frame = frame
                    self.latest_display_frame = display_frame
                    self.latest_results = current_results

                if self.on_frame_ready:
                    try:
                        self.on_frame_ready(display_frame, current_results)
                    except Exception as e:
                        logger.error(f"Error in on_frame_ready callback: {e}")

                # Brief sleep to avoid 100% CPU thread starvation
                time.sleep(0.005)

        except Exception as e:
            err = f"Camera error occurred during capture: {str(e)}"
            logger.exception(err)
            self._set_state(CameraState.ERROR, err)
        finally:
            if cap is not None:
                cap.release()
                logger.info(f"Released camera index {self.camera_index}.")

    def _update_stability_and_cooldown(
        self, results: List[BarcodeResult], current_time: float
    ) -> List[BarcodeResult]:
        """Track stability across consecutive frames and apply duplicate cooldown.
        
        Returns a list of newly confirmed BarcodeResult items that triggered confirmation.
        """
        confirmed = []
        visible_keys = set()

        for res in results:
            key = (res.barcode_type, res.data)
            visible_keys.add(key)

            # Increment consecutive detection count
            self._consecutive_counts[key] = self._consecutive_counts.get(key, 0) + 1

            # Check if threshold reached
            if self._consecutive_counts[key] >= self.stability_threshold:
                last_time = self._last_confirmed_timestamps.get(key, 0.0)
                # Check duplicate cooldown
                if current_time - last_time >= self.scan_cooldown_seconds:
                    self._last_confirmed_timestamps[key] = current_time
                    confirmed.append(res)
                    logger.info(f"Stable barcode confirmed: {res.barcode_type} ({res.data})")

        # Reset consecutive count for barcodes that are no longer visible in the frame
        keys_to_remove = [k for k in self._consecutive_counts if k not in visible_keys]
        for k in keys_to_remove:
            self._consecutive_counts.pop(k, None)

        return confirmed

    def _draw_reticle_guide(self, frame: np.ndarray):
        """Draw an unobtrusive scanning target guide box in the center of the frame."""
        h, w = frame.shape[:2]
        box_w = int(w * 0.65)
        box_h = int(h * 0.45)
        x1 = (w - box_w) // 2
        y1 = (h - box_h) // 2
        x2 = x1 + box_w
        y2 = y1 + box_h

        # Draw corner brackets
        corner_len = 24
        color = (180, 180, 180)
        thickness = 2

        # Top-left
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, thickness)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, thickness)
        # Top-right
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, thickness)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, thickness)
        # Bottom-left
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, thickness)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, thickness)
        # Bottom-right
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, thickness)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, thickness)
