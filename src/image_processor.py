"""Image loading, validation, quality metrics, preprocessing stages, and visual annotations."""

from pathlib import Path
from typing import Generator, List, Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image

from src.models import BarcodeResult, ImageMetrics
from src.utils import get_logger

logger = get_logger()

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_PROCESSING_DIMENSION = 3000  # Configurable max dimension to avoid memory bloat


class ImageProcessor:
    """Handles image validation, loading, quality inspection, multi-stage preprocessing, and annotation."""

    @staticmethod
    def is_valid_extension(file_path: Union[str, Path]) -> bool:
        """Check if file has a supported image extension."""
        path = Path(file_path)
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    @staticmethod
    def validate_file(file_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
        """Validate that file exists, is non-empty, and has a supported extension."""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return False, f"File does not exist: {path.name}"
            if not path.is_file():
                return False, f"Selected path is not a file: {path.name}"
            if path.stat().st_size == 0:
                return False, "Selected image file is empty (0 bytes)."
            if not ImageProcessor.is_valid_extension(path):
                exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))
                return False, (
                    f"Unsupported file format '{path.suffix}'.\n\n"
                    f"Please select a {', '.join(e.upper().replace('.', '') for e in sorted(SUPPORTED_EXTENSIONS))} image."
                )
            return True, None
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def load_image(file_path: Union[str, Path]) -> Optional[np.ndarray]:
        """Safely load an image from disk using numpy + cv2.imdecode (handles Unicode/Windows paths)."""
        path = Path(file_path).resolve()
        try:
            file_bytes = np.fromfile(str(path), dtype=np.uint8)
            if file_bytes.size == 0:
                logger.error(f"Failed to read bytes from {path}")
                return None
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                logger.error(f"OpenCV could not decode image at {path}")
                return None

            # Downscale safely if image exceeds maximum processing dimension (e.g. 8000x6000)
            h, w = image.shape[:2]
            if max(h, w) > MAX_PROCESSING_DIMENSION:
                scale = MAX_PROCESSING_DIMENSION / float(max(h, w))
                new_w, new_h = int(w * scale), int(h * scale)
                logger.info(
                    f"Downscaling huge image from {w}x{h} to {new_w}x{new_h} for memory safety"
                )
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

            return image
        except Exception as e:
            logger.error(f"Exception loading image {path}: {e}")
            return None

    @staticmethod
    def calculate_image_metrics(image: np.ndarray) -> ImageMetrics:
        """Calculate quality, brightness, contrast, and resolution metrics for an image."""
        h, w = image.shape[:2]
        channels = image.shape[2] if len(image.shape) == 3 else 1
        res_mp = round((w * h) / 1_000_000.0, 2)

        # Convert to grayscale for statistical analysis
        if channels == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        # Focus / Blur score via Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())

        warnings = []
        is_low_res = w < 300 or h < 200
        is_low_contrast = contrast < 30.0
        is_blurry = blur_score < 40.0

        if is_low_res:
            warnings.append("Low image resolution. Small barcodes may be difficult to detect.")
        if is_low_contrast:
            warnings.append("Low image contrast. Adaptive contrast enhancement will be used.")
        if is_blurry:
            warnings.append("Image appears slightly blurred or soft.")

        return ImageMetrics(
            width=w,
            height=h,
            channels=channels,
            resolution_mp=res_mp,
            brightness=round(brightness, 1),
            contrast=round(contrast, 1),
            blur_score=round(blur_score, 1),
            is_low_resolution=is_low_res,
            is_low_contrast=is_low_contrast,
            is_blurry=is_blurry,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Modular Preprocessing Filters
    # -------------------------------------------------------------------------
    @staticmethod
    def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
        """Convert image to grayscale array."""
        if len(image.shape) == 3 and image.shape[2] >= 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image.copy()

    @staticmethod
    def enhance_contrast(gray_image: np.ndarray, clip_limit: float = 3.0) -> np.ndarray:
        """Apply Contrast-Limited Adaptive Histogram Equalization (CLAHE)."""
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        return clahe.apply(gray_image)

    @staticmethod
    def apply_adaptive_threshold(gray_image: np.ndarray) -> np.ndarray:
        """Apply adaptive Gaussian thresholding."""
        return cv2.adaptiveThreshold(
            gray_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4
        )

    @staticmethod
    def apply_otsu_threshold(gray_image: np.ndarray) -> np.ndarray:
        """Apply Otsu binarization."""
        _, otsu = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return otsu

    @staticmethod
    def sharpen_image(gray_image: np.ndarray) -> np.ndarray:
        """Apply unsharp mask sharpening filter."""
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        return cv2.filter2D(gray_image, -1, kernel)

    @staticmethod
    def upscale_image(image: np.ndarray, factor: float = 2.0) -> np.ndarray:
        """Upscale image using bicubic interpolation."""
        h, w = image.shape[:2]
        new_w, new_h = int(w * factor), int(h * factor)
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    @staticmethod
    def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
        """Rotate image by 90, 180, or 270 degrees clockwise."""
        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return image.copy()

    @staticmethod
    def transform_point_to_original(
        pt: Tuple[int, int],
        orig_w: int,
        orig_h: int,
        rotation_angle: int = 0,
        scale_factor: float = 1.0,
    ) -> Tuple[int, int]:
        """Inverse transform coordinates from a rotated/scaled variant back to original image space."""
        xr = pt[0] / scale_factor
        yr = pt[1] / scale_factor

        if rotation_angle == 90:
            # 90° Clockwise inverse: original (orig_w, orig_h), rotated (orig_h, orig_w)
            x = yr
            y = orig_h - 1 - xr
        elif rotation_angle == 180:
            # 180° inverse
            x = orig_w - 1 - xr
            y = orig_h - 1 - yr
        elif rotation_angle == 270:
            # 270° Clockwise inverse
            x = orig_w - 1 - yr
            y = xr
        else:
            x = xr
            y = yr

        return max(0, min(orig_w - 1, int(round(x)))), max(0, min(orig_h - 1, int(round(y))))

    @staticmethod
    def preprocess_pipeline(
        image: np.ndarray,
    ) -> Generator[Tuple[str, np.ndarray, int, float], None, None]:
        """Generate controlled preprocessing variants for robust barcode detection.
        
        Yields (stage_name, processed_array, rotation_angle_deg, scale_factor)
        """
        # 1. Original Image (0°, 1.0x)
        yield "Original Image", image, 0, 1.0

        # Grayscale base
        gray = ImageProcessor.convert_to_grayscale(image)

        # 2. Grayscale (0°, 1.0x)
        yield "Grayscale Image", gray, 0, 1.0

        # 3. Contrast Enhanced CLAHE (0°, 1.0x)
        enhanced = ImageProcessor.enhance_contrast(gray)
        yield "Enhanced Contrast (CLAHE)", enhanced, 0, 1.0

        # 4. Otsu Threshold (0°, 1.0x)
        otsu = ImageProcessor.apply_otsu_threshold(gray)
        yield "Thresholded (Otsu)", otsu, 0, 1.0

        # 5. Adaptive Threshold (0°, 1.0x)
        adaptive = ImageProcessor.apply_adaptive_threshold(gray)
        yield "Adaptive Threshold", adaptive, 0, 1.0

        # 6. Scaled & Sharpened (0°, 2.0x if image < 2000px)
        h, w = gray.shape[:2]
        if max(h, w) < 2000:
            scaled = ImageProcessor.upscale_image(gray, 2.0)
            sharpened = ImageProcessor.sharpen_image(scaled)
            yield "Scaled & Sharpened", sharpened, 0, 2.0

        # 7-9. Rotations (90°, 180°, 270°) for difficult barcode orientations
        rot_90 = ImageProcessor.rotate_image(gray, 90)
        yield "Rotated 90°", rot_90, 90, 1.0

        rot_270 = ImageProcessor.rotate_image(gray, 270)
        yield "Rotated 270°", rot_270, 270, 1.0

        rot_180 = ImageProcessor.rotate_image(gray, 180)
        yield "Rotated 180°", rot_180, 180, 1.0

        # 10-11. Rotated + Enhanced Contrast
        rot_90_clahe = ImageProcessor.enhance_contrast(rot_90)
        yield "Rotated 90° (CLAHE)", rot_90_clahe, 90, 1.0

        rot_270_clahe = ImageProcessor.enhance_contrast(rot_270)
        yield "Rotated 270° (CLAHE)", rot_270_clahe, 270, 1.0

    @staticmethod
    def draw_bounding_boxes(
        image: np.ndarray,
        results: List[BarcodeResult],
        thickness: int = 3,
    ) -> np.ndarray:
        """Draw bounding boxes, polygons, and numbered tags on an image copy."""
        annotated = image.copy()
        h, w = annotated.shape[:2]

        # Distinct color palette for multiple barcodes (BGR format)
        palette = [
            (0, 210, 100),   # Emerald Green
            (255, 140, 0),   # Deep Sky Blue
            (0, 165, 255),   # Bright Orange
            (204, 50, 255),  # Violet / Purple
            (50, 205, 50),   # Lime Green
            (255, 215, 0),   # Golden Yellow
        ]

        for idx, result in enumerate(results, start=1):
            box_color = palette[(idx - 1) % len(palette)]
            tag_text = f"#{idx} {result.barcode_type}"

            # 1. Draw polygon if available
            if result.polygon and len(result.polygon) >= 3:
                pts = np.array(result.polygon, np.int32).reshape((-1, 1, 2))
                cv2.polylines(annotated, [pts], isClosed=True, color=box_color, thickness=thickness)
                bx, by, bw, bh = cv2.boundingRect(pts)
            else:
                bx, by, bw, bh = result.x, result.y, result.width, result.height
                if bw > 0 and bh > 0:
                    cv2.rectangle(
                        annotated,
                        (bx, by),
                        (bx + bw, by + bh),
                        box_color,
                        thickness,
                    )

            # 2. Draw styled tag badge with background pill
            if bw > 0 or bh > 0 or result.polygon:
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.55
                font_thickness = 1
                (tw, th), baseline = cv2.getTextSize(tag_text, font, font_scale, font_thickness)

                tag_x = max(5, min(bx, w - tw - 14))
                tag_y = by - 8 if by - th - 12 > 0 else by + th + 14

                # Dark background pill
                cv2.rectangle(
                    annotated,
                    (tag_x - 4, tag_y - th - 6),
                    (tag_x + tw + 6, tag_y + baseline + 2),
                    (20, 24, 30),
                    cv2.FILLED,
                )
                # Colored border on badge pill
                cv2.rectangle(
                    annotated,
                    (tag_x - 4, tag_y - th - 6),
                    (tag_x + tw + 6, tag_y + baseline + 2),
                    box_color,
                    1,
                )
                # White text
                cv2.putText(
                    annotated,
                    tag_text,
                    (tag_x, tag_y),
                    font,
                    font_scale,
                    (255, 255, 255),
                    font_thickness,
                    cv2.LINE_AA,
                )

        return annotated

    @staticmethod
    def resize_for_preview(
        image: Union[np.ndarray, Image.Image],
        max_width: int = 560,
        max_height: int = 420,
    ) -> Image.Image:
        """Resize image to fit within max dimensions while strictly preserving aspect ratio."""
        if isinstance(image, np.ndarray):
            if len(image.shape) == 3:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            pil_img = Image.fromarray(rgb)
        else:
            pil_img = image.copy()

        orig_w, orig_h = pil_img.size
        if orig_w <= 0 or orig_h <= 0:
            return pil_img

        scale = min(max_width / orig_w, max_height / orig_h)
        if scale < 1.0:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            return pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        return pil_img
