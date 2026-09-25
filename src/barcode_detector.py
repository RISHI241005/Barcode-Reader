"""Barcode and QR code detection, decoding, rotation handling, and deduplication engine."""

import time
import numpy as np  # pyrefly: ignore [missing-import] # type: ignore
from typing import List, Optional, Tuple

try:
    from src.models import BarcodeResult, DetectionReport  # pyrefly: ignore [missing-import] # type: ignore
    from src.image_processor import ImageProcessor  # pyrefly: ignore [missing-import] # type: ignore
    from src.utils import get_logger, normalize_barcode_type, validate_barcode_checksum  # pyrefly: ignore [missing-import] # type: ignore
except (ImportError, ModuleNotFoundError):
    from models import BarcodeResult, DetectionReport  # pyrefly: ignore [missing-import] # type: ignore
    from image_processor import ImageProcessor  # pyrefly: ignore [missing-import] # type: ignore
    from utils import get_logger, normalize_barcode_type, validate_barcode_checksum  # pyrefly: ignore [missing-import] # type: ignore

logger = get_logger()

# Check available decoding engines (conditional for serverless compatibility)
try:
    import cv2  # pyrefly: ignore [missing-import] # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import zxingcpp  # pyrefly: ignore [missing-import] # type: ignore
    HAS_ZXING = True
except ImportError:
    HAS_ZXING = False

try:
    import os
    import sys
    from pathlib import Path
    if sys.platform == "win32":
        try:
            import pyzbar  # pyrefly: ignore [missing-import] # type: ignore
            pyzbar_dir = Path(pyzbar.__file__).parent
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(pyzbar_dir))
        except Exception:
            pass
    from pyzbar import pyzbar as pyzbar_module  # pyrefly: ignore [missing-import] # type: ignore
    HAS_PYZBAR = True
except Exception:
    HAS_PYZBAR = False


def _compute_box_iou(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
    """Calculate Intersection over Union (IoU) between two bounding boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)
    iw = max(0, xi2 - xi1)
    ih = max(0, yi2 - yi1)
    ia = iw * ih
    ua = (w1 * h1) + (w2 * h2) - ia
    return float(ia) / float(ua) if ua > 0 else 0.0


def _is_duplicate(r1: BarcodeResult, r2: BarcodeResult) -> bool:
    """Check if two detected results represent the same physical barcode in an image."""
    data_match = (r1.data == r2.data)
    if not data_match:
        if (r1.data == "0" + r2.data) or (r2.data == "0" + r1.data):
            data_match = True

    if not data_match:
        return False

    type_match = (r1.barcode_type == r2.barcode_type)
    if not type_match:
        ean_upc = {"EAN-13", "UPC-A", "UPC-E", "EAN-8"}
        qr_family = {"QR Code", "Micro QR Code"}
        if (r1.barcode_type in ean_upc and r2.barcode_type in ean_upc) or \
           (r1.barcode_type in qr_family and r2.barcode_type in qr_family) or \
           (r1.barcode_type == "Barcode" or r2.barcode_type == "Barcode"):
            type_match = True

    if not type_match:
        return False

    # If either result lacks valid dimensions, treat matching data and type as duplicate
    if (r1.width <= 0 or r1.height <= 0) or (r2.width <= 0 or r2.height <= 0):
        return True
    
    # 1. IoU check
    iou = _compute_box_iou(r1.bounding_box, r2.bounding_box)
    if iou > 0.20:
        return True

    # 2. Center proximity check (within 40px or 45% of box dimension)
    c1 = r1.center
    c2 = r2.center
    dist = ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5
    avg_dim = (r1.width + r1.height + r2.width + r2.height) / 4.0
    if dist < max(35.0, avg_dim * 0.45):
        return True

    return False


class BarcodeDetector:
    """Advanced barcode detector with multi-engine, multi-stage fallback and rotation handling."""

    def __init__(self):
        self.has_zxing = HAS_ZXING
        self.has_pyzbar = HAS_PYZBAR
        self.has_cv2 = HAS_CV2
        self.cv_barcode_detector = None
        self.cv_qr_detector = None

        if self.has_cv2 and hasattr(cv2, "barcode") and hasattr(cv2.barcode, "BarcodeDetector"):
            try:
                self.cv_barcode_detector = cv2.barcode.BarcodeDetector()
            except Exception as e:
                logger.debug(f"OpenCV BarcodeDetector init failed: {e}")

        if self.has_cv2 and hasattr(cv2, "QRCodeDetector"):
            try:
                self.cv_qr_detector = cv2.QRCodeDetector()
            except Exception as e:
                logger.debug(f"OpenCV QRCodeDetector init failed: {e}")

        logger.info(
            f"BarcodeDetector initialized (ZXing-C++: {self.has_zxing}, "
            f"PyZBar: {self.has_pyzbar}, OpenCV: {self.has_cv2 and self.cv_barcode_detector is not None})"
        )

    def detect_and_decode(self, image: np.ndarray, fast_mode: bool = False) -> DetectionReport:
        """Run barcode detection across the controlled multi-stage fallback pipeline.
        
        Evaluates preprocessing stages and applies deduplication and checksum validation.
        When fast_mode=True (for live camera scanning), restricts to lightweight passes for maximum FPS.
        """
        start_time = time.perf_counter()

        if image is None or image.size == 0:
            return DetectionReport(
                success=False,
                results=[],
                stage_used="None",
                processing_time_ms=0.0,
                error_message="Image is empty or could not be loaded.",
            )

        orig_h, orig_w = image.shape[:2]
        metrics = None
        if not fast_mode:
            metrics = ImageProcessor.calculate_image_metrics(image)
            logger.info(
                f"Starting barcode detection on image: {metrics.dimensions_str} "
                f"({metrics.resolution_mp} MP, Brightness: {metrics.brightness}, Contrast: {metrics.contrast})"
            )

        all_results: List[BarcodeResult] = []
        stages_attempted: List[str] = []
        successful_stages: List[str] = []
        engine_name = "ZXing-C++" if self.has_zxing else ("PyZBar" if self.has_pyzbar else "OpenCV")

        pipeline = ImageProcessor.preprocess_pipeline(image)
        stages_without_new = 0

        for stage_name, proc_img, rot_angle, scale_factor in pipeline:
            stages_attempted.append(stage_name)
            logger.debug(f"Attempting stage: {stage_name} (Rot: {rot_angle}°, Scale: {scale_factor}x)")

            # Decode current variant
            raw_stage_results = self._decode_single_variant(
                proc_img, orig_w, orig_h, rot_angle, scale_factor, stage_name
            )

            # Deduplicate and merge results
            new_added = False
            for cand in raw_stage_results:
                # Perform checksum validation
                val_status, val_details = validate_barcode_checksum(cand.barcode_type, cand.data)
                cand.validation_status = val_status
                cand.validation_details = val_details

                # Check if candidate is already in all_results
                duplicate_found = False
                for i, existing in enumerate(all_results):
                    if _is_duplicate(existing, cand):
                        duplicate_found = True
                        if existing.barcode_type == "Barcode" and cand.barcode_type != "Barcode":
                            all_results[i] = cand
                        elif (existing.width <= 0 or existing.height <= 0) and (cand.width > 0 and cand.height > 0):
                            all_results[i] = cand
                        break

                if not duplicate_found:
                    all_results.append(cand)
                    new_added = True

            if new_added:
                stages_without_new = 0
                successful_stages.append(stage_name)
                logger.info(
                    f"Stage '{stage_name}' yielded {len(raw_stage_results)} detection(s)."
                )
            else:
                stages_without_new += 1

            # Camera fast_mode optimization:
            # Evaluate the first 2 fast stages (Original + Grayscale) to capture all barcodes and QR codes without FPS drop
            if fast_mode:
                if len(stages_attempted) >= 2:
                    break
            else:
                # Standard image mode:
                # Allow comprehensive passes so all barcodes and QR codes in the image are found.
                # Stop if core passes completed and no new barcodes were found for 3 consecutive stages.
                if len(all_results) > 0 and len(stages_attempted) >= 5 and stages_without_new >= 3:
                    break

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        success = len(all_results) > 0

        summary_stage = ", ".join(successful_stages) if successful_stages else "None (All stages attempted)"

        if success:
            logger.info(
                f"Detection completed in {elapsed_ms:.1f}ms: found {len(all_results)} barcode(s) "
                f"via [{summary_stage}]"
            )
        else:
            logger.info(f"No barcodes detected across {len(stages_attempted)} stages in {elapsed_ms:.1f}ms")

        return DetectionReport(
            success=success,
            results=all_results,
            stage_used=summary_stage,
            processing_time_ms=round(elapsed_ms, 2),
            engine_used=engine_name,
            image_metrics=metrics,
            stages_attempted=stages_attempted,
            error_message=None if success else "No barcode detected in the uploaded image.",
        )

    def _decode_single_variant(
        self,
        img: np.ndarray,
        orig_w: int,
        orig_h: int,
        rot_angle: int,
        scale_factor: float,
        stage_name: str,
    ) -> List[BarcodeResult]:
        """Attempt barcode decoding on an individual image variant and map coordinates back.
        
        Runs all available decoding engines (ZXing-C++, PyZBar, OpenCV Barcode, OpenCV QR)
        and merges detected barcodes and QR codes simultaneously.
        """
        results: List[BarcodeResult] = []

        def _add_if_new(candidate: BarcodeResult):
            for i, existing in enumerate(results):
                if _is_duplicate(existing, candidate):
                    if existing.barcode_type == "Barcode" and candidate.barcode_type != "Barcode":
                        results[i] = candidate
                    elif (existing.width <= 0 or existing.height <= 0) and (candidate.width > 0 and candidate.height > 0):
                        results[i] = candidate
                    return
            results.append(candidate)

        # 1. Primary engine: ZXing-C++
        if self.has_zxing:
            try:
                zxing_results = zxingcpp.read_barcodes(
                    img,
                    try_rotate=True,
                    try_downscale=True,
                    try_invert=True,
                )
                for res in zxing_results:
                    if hasattr(res, "valid") and not res.valid and not res.text:
                        continue
                    if not res.text and not getattr(res, "bytes", None):
                        continue

                    raw_type_str = str(res.format).replace("BarcodeFormat.", "").replace("Format.", "")
                    clean_type = normalize_barcode_type(raw_type_str)
                    data_str = (
                        res.text
                        if res.text
                        else (res.bytes.decode("utf-8", errors="replace") if hasattr(res, "bytes") else "")
                    )

                    # Extract polygon and transform back to original image space
                    polygon: List[Tuple[int, int]] = []
                    pos = res.position
                    if pos is not None:
                        variant_pts = [
                            (pos.top_left.x, pos.top_left.y),
                            (pos.top_right.x, pos.top_right.y),
                            (pos.bottom_right.x, pos.bottom_right.y),
                            (pos.bottom_left.x, pos.bottom_left.y),
                        ]
                        polygon = [
                            ImageProcessor.transform_point_to_original(
                                pt, orig_w, orig_h, rot_angle, scale_factor
                            )
                            for pt in variant_pts
                        ]
                        xs = [p[0] for p in polygon]
                        ys = [p[1] for p in polygon]
                        bx = max(0, min(xs))
                        by = max(0, min(ys))
                        bw = max(0, max(xs) - bx)
                        bh = max(0, max(ys) - by)
                    else:
                        bx, by, bw, bh = 0, 0, 0, 0

                    _add_if_new(
                        BarcodeResult(
                            barcode_type=clean_type,
                            raw_type=raw_type_str,
                            data=data_str,
                            x=bx,
                            y=by,
                            width=bw,
                            height=bh,
                            polygon=polygon,
                            rotation=rot_angle,
                            processing_method=stage_name,
                        )
                    )
            except Exception as e:
                logger.debug(f"ZXing-C++ decode error in stage {stage_name}: {e}")

        # 2. Secondary engine: PyZBar (if available)
        if self.has_pyzbar:
            try:
                pyz_results = pyzbar_module.decode(img)
                for res in pyz_results:
                    raw_type = str(res.type)
                    clean_type = normalize_barcode_type(raw_type)
                    try:
                        data_str = res.data.decode("utf-8")
                    except UnicodeDecodeError:
                        data_str = res.data.decode("latin-1", errors="replace")

                    rect = res.rect
                    var_corners = [
                        (rect.left, rect.top),
                        (rect.left + rect.width, rect.top),
                        (rect.left + rect.width, rect.top + rect.height),
                        (rect.left, rect.top + rect.height),
                    ]
                    if hasattr(res, "polygon") and res.polygon and len(res.polygon) >= 3:
                        var_corners = [(p.x, p.y) for p in res.polygon]

                    orig_corners = [
                        ImageProcessor.transform_point_to_original(
                            pt, orig_w, orig_h, rot_angle, scale_factor
                        )
                        for pt in var_corners
                    ]
                    xs = [p[0] for p in orig_corners]
                    ys = [p[1] for p in orig_corners]
                    bx = max(0, min(xs))
                    by = max(0, min(ys))
                    bw = max(0, max(xs) - bx)
                    bh = max(0, max(ys) - by)

                    _add_if_new(
                        BarcodeResult(
                            barcode_type=clean_type,
                            raw_type=raw_type,
                            data=data_str,
                            x=bx,
                            y=by,
                            width=bw,
                            height=bh,
                            polygon=orig_corners,
                            rotation=rot_angle,
                            processing_method=stage_name,
                        )
                    )
            except Exception as e:
                logger.debug(f"PyZBar decode error in stage {stage_name}: {e}")

        # 3. Tertiary complementary engine: OpenCV 1D Barcode Detector
        if self.cv_barcode_detector is not None:
            try:
                ret = self.cv_barcode_detector.detectAndDecodeMulti(img)
                if ret and len(ret) >= 3 and ret[0]:
                    decoded_info = ret[1]
                    corners = ret[2]
                    decoded_type = ret[3] if len(ret) > 3 else []
                    if decoded_info is not None:
                        for i, text in enumerate(decoded_info):
                            if text:
                                btype = decoded_type[i] if (decoded_type is not None and len(decoded_type) > i) else "Barcode"
                                clean_type = normalize_barcode_type(btype if btype else "Barcode")
                                corner_set = corners[i] if (corners is not None and len(corners) > i) else []
                                orig_poly = []
                                if corner_set is not None and len(corner_set) > 0:
                                    orig_poly = [
                                        ImageProcessor.transform_point_to_original(
                                            (int(pt[0]), int(pt[1])), orig_w, orig_h, rot_angle, scale_factor
                                        )
                                        for pt in corner_set
                                    ]
                                xs = [p[0] for p in orig_poly] if orig_poly else [0]
                                ys = [p[1] for p in orig_poly] if orig_poly else [0]
                                bx = max(0, min(xs))
                                by = max(0, min(ys))
                                bw = max(0, max(xs) - bx)
                                bh = max(0, max(ys) - by)
                                _add_if_new(
                                    BarcodeResult(
                                        barcode_type=clean_type,
                                        raw_type=str(btype),
                                        data=str(text),
                                        x=bx,
                                        y=by,
                                        width=bw,
                                        height=bh,
                                        polygon=orig_poly,
                                        rotation=rot_angle,
                                        processing_method=stage_name,
                                    )
                                )
            except Exception as e:
                logger.debug(f"OpenCV BarcodeDetector error in stage {stage_name}: {e}")

        # 4. Tertiary complementary engine: OpenCV QR Code Detector (Always run alongside barcode detector)
        if self.cv_qr_detector is not None:
            try:
                ret = self.cv_qr_detector.detectAndDecodeMulti(img)
                if ret and len(ret) >= 3 and ret[0]:
                    decoded_info = ret[1]
                    points = ret[2]
                    if decoded_info is not None and points is not None:
                        for text, corner_set in zip(decoded_info, points):
                            if text:
                                orig_poly = []
                                if corner_set is not None and len(corner_set) > 0:
                                    orig_poly = [
                                        ImageProcessor.transform_point_to_original(
                                            (int(pt[0]), int(pt[1])), orig_w, orig_h, rot_angle, scale_factor
                                        )
                                        for pt in corner_set
                                    ]
                                xs = [p[0] for p in orig_poly] if orig_poly else [0]
                                ys = [p[1] for p in orig_poly] if orig_poly else [0]
                                bx = max(0, min(xs))
                                by = max(0, min(ys))
                                bw = max(0, max(xs) - bx)
                                bh = max(0, max(ys) - by)
                                _add_if_new(
                                    BarcodeResult(
                                        barcode_type="QR Code",
                                        raw_type="QRCODE",
                                        data=str(text),
                                        x=bx,
                                        y=by,
                                        width=bw,
                                        height=bh,
                                        polygon=orig_poly,
                                        rotation=rot_angle,
                                        processing_method=stage_name,
                                    )
                                )
            except Exception as e:
                logger.debug(f"OpenCV QRCodeDetector error in stage {stage_name}: {e}")

        return results
