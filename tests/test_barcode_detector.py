"""Comprehensive unit and integration tests for BarcodeDetector (Part 2)."""

from pathlib import Path
import pytest  # pyrefly: ignore [missing-import] # type: ignore
import numpy as np  # pyrefly: ignore [missing-import] # type: ignore
import cv2  # pyrefly: ignore [missing-import] # type: ignore

try:
    from src.barcode_detector import BarcodeDetector, _is_duplicate  # pyrefly: ignore [missing-import] # type: ignore
    from src.image_processor import ImageProcessor  # pyrefly: ignore [missing-import] # type: ignore
    from src.models import BarcodeResult  # pyrefly: ignore [missing-import] # type: ignore
    from src.utils import normalize_barcode_type, validate_barcode_checksum  # pyrefly: ignore [missing-import] # type: ignore
except (ImportError, ModuleNotFoundError):
    from barcode_detector import BarcodeDetector, _is_duplicate  # pyrefly: ignore [missing-import] # type: ignore
    from image_processor import ImageProcessor  # pyrefly: ignore [missing-import] # type: ignore
    from models import BarcodeResult  # pyrefly: ignore [missing-import] # type: ignore
    from utils import normalize_barcode_type, validate_barcode_checksum  # pyrefly: ignore [missing-import] # type: ignore

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_images"


@pytest.fixture(scope="module")
def detector():
    """BarcodeDetector instance fixture."""
    return BarcodeDetector()


def test_ean13_detection_and_checksum(detector):
    """Test 1: Valid EAN-13 barcode detection, data decoding, and Mod 10 checksum validation."""
    img_path = SAMPLE_DIR / "ean13_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.count >= 1
    
    result = report.results[0]
    assert result.barcode_type == "EAN-13"
    assert result.data == "8901234567890"
    assert result.validation_status == "Valid"
    assert "Modulo 10" in (result.validation_details or "")


def test_qrcode_detection(detector):
    """Test 2: Valid QR Code detection and URL data extraction."""
    img_path = SAMPLE_DIR / "qrcode_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.count >= 1
    
    result = report.results[0]
    assert result.barcode_type == "QR Code"
    assert result.data == "https://example.com"


def test_code128_detection(detector):
    """Test 3: Valid Code 128 detection and alphanumeric data extraction."""
    img_path = SAMPLE_DIR / "code128_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.count >= 1
    
    result = report.results[0]
    assert result.barcode_type == "Code 128"
    assert result.data == "PRODUCT-10234"


def test_multiple_barcodes_detection(detector):
    """Test 4: Multiple distinct barcodes detected in a single composite image."""
    img_path = SAMPLE_DIR / "multiple_barcodes_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.count >= 3
    
    types = [r.barcode_type for r in report.results]
    data_list = [r.data for r in report.results]
    
    assert "EAN-13" in types
    assert "QR Code" in types
    assert "Code 128" in types
    assert "8901234567890" in data_list
    assert "https://example.com" in data_list
    assert "PRODUCT-123" in data_list


def test_duplicate_detection_prevention():
    """Test 5: Verify that duplicate candidates with overlapping boxes are recognized as duplicates."""
    r1 = BarcodeResult(
        barcode_type="EAN-13",
        raw_type="EAN13",
        data="8901234567890",
        x=100,
        y=100,
        width=200,
        height=100,
    )
    # Slightly shifted box (from another preprocessing pass)
    r2 = BarcodeResult(
        barcode_type="EAN-13",
        raw_type="EAN13",
        data="8901234567890",
        x=103,
        y=98,
        width=198,
        height=102,
    )
    # Different location (different barcode with same data)
    r3 = BarcodeResult(
        barcode_type="EAN-13",
        raw_type="EAN13",
        data="8901234567890",
        x=600,
        y=500,
        width=200,
        height=100,
    )
    
    assert _is_duplicate(r1, r2) is True
    assert _is_duplicate(r1, r3) is False


def test_rotated_barcodes_detection(detector):
    """Test 6: Detection of barcodes rotated by 90°, 180°, and 270°."""
    # 90° Rotated EAN-13
    img_90 = ImageProcessor.load_image(SAMPLE_DIR / "ean13_rotated90.png")
    assert img_90 is not None
    rep_90 = detector.detect_and_decode(img_90)
    assert rep_90.success is True
    assert rep_90.results[0].data == "8901234567890"

    # 180° Rotated Code 128
    img_180 = ImageProcessor.load_image(SAMPLE_DIR / "code128_rotated180.png")
    assert img_180 is not None
    rep_180 = detector.detect_and_decode(img_180)
    assert rep_180.success is True
    assert rep_180.results[0].data == "ROTATED-180"

    # 270° Rotated QR Code
    img_270 = ImageProcessor.load_image(SAMPLE_DIR / "qrcode_rotated270.png")
    assert img_270 is not None
    rep_270 = detector.detect_and_decode(img_270)
    assert rep_270.success is True
    assert rep_270.results[0].data == "https://antigravity.dev/part2"


def test_low_contrast_fallback_detection(detector):
    """Test 7: Fallback preprocessing recovers low-contrast barcode."""
    img_path = SAMPLE_DIR / "low_contrast_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.count >= 1
    assert report.results[0].data == "8901234567890"


def test_small_barcode_detection(detector):
    """Test 8: Small barcode within large container is detected."""
    img_path = SAMPLE_DIR / "small_barcode_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is True
    assert report.results[0].data == "SMALL-77"


def test_no_barcode_in_image(detector):
    """Test 9: Image without barcodes returns graceful empty report without error."""
    img_path = SAMPLE_DIR / "no_barcode_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img)
    assert report.success is False
    assert report.count == 0
    assert report.error_message is not None


def test_empty_and_corrupted_inputs(detector):
    """Test 10: Empty, None, or zero-byte arrays handled safely."""
    empty_img = np.array([], dtype=np.uint8)
    rep_empty = detector.detect_and_decode(empty_img)
    assert rep_empty.success is False

    rep_none = detector.detect_and_decode(None)
    assert rep_none.success is False


def test_checksum_validations():
    """Test 11: Validation functions for EAN-13, EAN-8, UPC-A, UPC-E, and invalid check digits."""
    # EAN-13 Valid
    v, d = validate_barcode_checksum("EAN-13", "8901234567890")
    assert v == "Valid"

    # EAN-13 Invalid Check Digit
    v, d = validate_barcode_checksum("EAN-13", "8901234567899")
    assert v == "Invalid"

    # EAN-8 Valid
    v, d = validate_barcode_checksum("EAN-8", "96385074")
    assert v == "Valid"

    # UPC-A Valid
    v, d = validate_barcode_checksum("UPC-A", "012345678905")
    assert v == "Valid"

    # UPC-E Valid
    v, d = validate_barcode_checksum("UPC-E", "01234565")
    assert v == "Valid"

    # QR Code (Not Applicable)
    v, d = validate_barcode_checksum("QR Code", "https://example.com")
    assert v == "Not Available"


def test_simultaneous_fast_mode_multiple_codes(detector):
    """Test 12: Verify fast_mode=True (camera scanning mode) decodes multiple barcodes simultaneously without early exit."""
    img_path = SAMPLE_DIR / "multiple_barcodes_sample.png"
    assert img_path.exists()
    
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    report = detector.detect_and_decode(img, fast_mode=True)
    assert report.success is True
    assert report.count >= 3
    types = [r.barcode_type for r in report.results]
    assert "QR Code" in types
    assert "EAN-13" in types
    assert "Code 128" in types
