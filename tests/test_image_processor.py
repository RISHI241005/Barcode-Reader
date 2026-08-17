"""Comprehensive unit tests for ImageProcessor module (Part 2)."""

from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from src.image_processor import ImageProcessor, MAX_PROCESSING_DIMENSION
from src.models import BarcodeResult

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_images"


def test_extension_validation():
    """Test supported and unsupported extension checks."""
    assert ImageProcessor.is_valid_extension("sample.jpg") is True
    assert ImageProcessor.is_valid_extension("sample.JPEG") is True
    assert ImageProcessor.is_valid_extension("sample.png") is True
    assert ImageProcessor.is_valid_extension("sample.bmp") is True
    assert ImageProcessor.is_valid_extension("sample.webp") is True
    
    assert ImageProcessor.is_valid_extension("sample.pdf") is False
    assert ImageProcessor.is_valid_extension("sample.txt") is False
    assert ImageProcessor.is_valid_extension("sample.exe") is False
    assert ImageProcessor.is_valid_extension("sample.gif") is False


def test_file_validation_nonexistent():
    """Test validation fails gracefully for nonexistent files."""
    is_valid, msg = ImageProcessor.validate_file("non_existent_file_xyz_123.png")
    assert is_valid is False
    assert "does not exist" in msg.lower() or "not a file" in msg.lower()


def test_file_validation_valid():
    """Test validation succeeds on real sample images."""
    img_path = SAMPLE_DIR / "ean13_sample.png"
    assert img_path.exists()
    is_valid, msg = ImageProcessor.validate_file(img_path)
    assert is_valid is True
    assert msg is None


def test_safe_image_loading():
    """Test safe image loading with OpenCV."""
    img_path = SAMPLE_DIR / "qrcode_sample.png"
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3
    assert img.shape[0] > 0
    assert img.shape[1] > 0


def test_huge_image_downscaling():
    """Test that oversized images (e.g. 4000x3000) are safely capped to MAX_PROCESSING_DIMENSION."""
    huge_arr = np.ones((4000, 3000, 3), dtype=np.uint8) * 200
    tmp_path = SAMPLE_DIR / "temp_huge.png"
    Image.fromarray(huge_arr).save(tmp_path)
    
    try:
        loaded = ImageProcessor.load_image(tmp_path)
        assert loaded is not None
        assert max(loaded.shape[:2]) <= MAX_PROCESSING_DIMENSION
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_calculate_image_metrics():
    """Test image quality metric computation (resolution, brightness, contrast, blur score)."""
    img_path = SAMPLE_DIR / "ean13_sample.png"
    img = ImageProcessor.load_image(img_path)
    assert img is not None
    
    metrics = ImageProcessor.calculate_image_metrics(img)
    assert metrics.width == img.shape[1]
    assert metrics.height == img.shape[0]
    assert metrics.brightness >= 0.0
    assert metrics.contrast >= 0.0
    assert isinstance(metrics.warnings, list)


def test_coordinate_inverse_transform():
    """Test transformation of coordinates from rotated and scaled images back to original space."""
    orig_w, orig_h = 400, 200

    # 0° rotation, 1.0x scale
    p0 = ImageProcessor.transform_point_to_original((50, 30), orig_w, orig_h, 0, 1.0)
    assert p0 == (50, 30)

    # 90° rotation inverse
    # Point at (30, orig_w - 1 - 50) = (30, 349)
    rot_x = orig_h - 1 - 30
    rot_y = 50
    p90 = ImageProcessor.transform_point_to_original((rot_x, rot_y), orig_w, orig_h, 90, 1.0)
    assert p90 == (50, 30)

    # 180° rotation inverse
    p180 = ImageProcessor.transform_point_to_original((orig_w - 1 - 50, orig_h - 1 - 30), orig_w, orig_h, 180, 1.0)
    assert p180 == (50, 30)

    # 2.0x scale
    p_scale = ImageProcessor.transform_point_to_original((100, 60), orig_w, orig_h, 0, 2.0)
    assert p_scale == (50, 30)


def test_preview_resizing_aspect_ratio():
    """Test that preview resizing strictly preserves aspect ratio."""
    wide_img = Image.new("RGB", (800, 400), color=(255, 255, 255))
    resized_wide = ImageProcessor.resize_for_preview(wide_img, max_width=400, max_height=400)
    w, h = resized_wide.size
    assert w == 400
    assert h == 200
    assert abs((w / h) - 2.0) < 0.01


def test_draw_bounding_boxes():
    """Test bounding box drawing on image copies without mutating original."""
    orig_img = np.zeros((400, 400, 3), dtype=np.uint8)
    sample_result = BarcodeResult(
        barcode_type="EAN-13",
        raw_type="EAN13",
        data="8901234567890",
        x=50,
        y=50,
        width=150,
        height=100,
        polygon=[(50, 50), (200, 50), (200, 150), (50, 150)],
    )

    annotated = ImageProcessor.draw_bounding_boxes(orig_img, [sample_result])
    assert annotated is not None
    assert np.array_equal(orig_img, np.zeros((400, 400, 3), dtype=np.uint8))
    assert not np.array_equal(annotated, orig_img)
