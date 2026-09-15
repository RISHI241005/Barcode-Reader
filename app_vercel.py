"""Vercel-deployable FastAPI entry point for Barcode Reader.

Exposes /detect-barcode endpoint for barcode/QR code detection from images.
Uses lazy detector initialization to handle serverless import issues.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Barcode Reader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_detector = None
_detector_error = None


def _get_detector():
    """Lazy-load barcode detector to handle import issues in serverless environments."""
    global _detector
    global _detector_error

    if _detector is not None:
        return _detector

    if _detector_error is not None:
        return None

    try:
        from src.barcode_detector import BarcodeDetector
        _detector = BarcodeDetector()
        return _detector
    except Exception as exc:
        _detector_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Failed to initialize barcode detector")
        return None


@app.get("/api")
async def health_check():
    """Health check endpoint that verifies the API is running.

    Does NOT initialize the barcode detector, allowing Vercel health checks
    to work independently of native barcode dependencies.
    """
    detector = _get_detector()
    return {
        "status": "ok",
        "service": "barcode-reader-api",
        "detector_initialized": _detector is not None,
        "detector_error": _detector_error,
    }


@app.post("/api/detect-barcode")
async def detect_barcode(file: UploadFile = File(...)):
    """Detect and decode barcodes/QR codes from an uploaded image file.

    Returns detection results including barcode type, data, and validation status.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Read the uploaded file into memory
    image_data = await file.read()
    if not image_data:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Convert to OpenCV format
    try:
        pil_image = Image.open(io.BytesIO(image_data))
        cv_image = _pil_to_cv_image(pil_image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")

    # Run barcode detection (lazy initialization)
    detector = _get_detector()

    if detector is None:
        raise HTTPException(
            status_code=503,
            detail="Barcode detector unavailable. Check serverless environment compatibility.",
        )

    report = detector.detect_and_decode(cv_image, fast_mode=False)

    if not report.success or not report.results:
        return {
            "success": False,
            "results": [],
            "message": "No barcodes detected in the image.",
            "engine_used": getattr(report, 'engine_used', 'Unknown'),
            "processing_time_ms": getattr(report, 'processing_time_ms', 0.0),
        }

    results = []
    for result in report.results:
        results.append({
            "barcode_type": result.barcode_type,
            "raw_type": result.raw_type,
            "data": result.data,
            "x": result.x,
            "y": result.y,
            "width": result.width,
            "height": result.height,
            "validation_status": result.validation_status,
            "validation_details": result.validation_details,
            "confidence": result.confidence,
            "processing_method": result.processing_method,
        })

    return {
        "success": True,
        "results": results,
        "engine_used": getattr(report, 'engine_used', 'Unknown'),
        "processing_time_ms": getattr(report, 'processing_time_ms', 0.0),
        "stages_attempted": getattr(report, 'stages_attempted', []),
    }


def _pil_to_cv_image(pil_image):
    """Convert a PIL image to OpenCV format.
    
    This import is lazy to avoid cv2 module-level import issues in serverless environments.
    """
    import cv2
    import numpy as np
    
    cv_image = np.array(pil_image)
    # Convert RGB to BGR for OpenCV
    if len(cv_image.shape) == 3:
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)
    elif len(cv_image.shape) == 2:
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_GRAY2BGR)
    return cv_image