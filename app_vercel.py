"""Vercel-deployable FastAPI entry point for Barcode Reader."""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from PIL import Image
import io
import cv2

from src.barcode_detector import BarcodeDetector
from src.image_processor import ImageProcessor
from src.models import BarcodeResult, DetectionReport
from src.utils import normalize_barcode_type

app = FastAPI(title="Barcode Reader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

detector = BarcodeDetector()


@app.post("/detect-barcode/")
async def detect_barcode(file: UploadFile = File(...)):
    """Detect and decode barcodes/QR codes from an uploaded image file.

    Returns detection results including barcode type, data, and confidence.
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
        cv_image = np.array(pil_image)
        # Convert RGB to BGR for OpenCV
        if len(cv_image.shape) == 3:
            cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)
        elif len(cv_image.shape) == 2:
            cv_image = cv2.cvtColor(cv_image, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")

    # Run barcode detection
    report = detector.detect_and_decode(cv_image, fast_mode=False)

    if not report.success or not report.results:
        return {
            "success": False,
            "results": [],
            "message": "No barcodes detected in the image.",
            "engine_used": report.engine_used,
            "processing_time_ms": report.processing_time_ms,
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
        "engine_used": report.engine_used,
        "processing_time_ms": report.processing_time_ms,
        "stages_attempted": report.stages_attempted,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)