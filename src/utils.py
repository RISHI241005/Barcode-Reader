"""Utility functions for logging, barcode format formatting, checksum validation, and clipboard."""

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import tkinter as tk
except ImportError:
    tk = None

# Supported format name mapping to user-friendly display names
FORMAT_NAME_MAP: Dict[str, str] = {
    "EAN_13": "EAN-13",
    "EAN13": "EAN-13",
    "EAN_8": "EAN-8",
    "EAN8": "EAN-8",
    "UPC_A": "UPC-A",
    "UPCA": "UPC-A",
    "UPC_E": "UPC-E",
    "UPCE": "UPC-E",
    "CODE_39": "Code 39",
    "CODE39": "Code 39",
    "CODE_93": "Code 93",
    "CODE93": "Code 93",
    "CODE_128": "Code 128",
    "CODE128": "Code 128",
    "ITF": "ITF",
    "ITF-14": "ITF-14",
    "I25": "ITF",
    "QR_CODE": "QR Code",
    "QRCODE": "QR Code",
    "QR CODE": "QR Code",
    "MICRO_QR_CODE": "Micro QR Code",
    "DATA_MATRIX": "Data Matrix",
    "DATAMATRIX": "Data Matrix",
    "AZTEC": "Aztec Code",
    "PDF_417": "PDF-417",
    "PDF417": "PDF-417",
    "CODABAR": "Codabar",
    "DATABAR": "GS1 DataBar",
    "DATABAR_EXPANDED": "GS1 DataBar Expanded",
}


def normalize_barcode_type(raw_type: str) -> str:
    """Convert raw decoder format name to clean user-facing format name."""
    if not raw_type:
        return "Unknown"
    
    cleaned = str(raw_type).strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in FORMAT_NAME_MAP:
        return FORMAT_NAME_MAP[cleaned]
    
    # Direct check against original string
    raw_upper = str(raw_type).strip().upper()
    if raw_upper in FORMAT_NAME_MAP:
        return FORMAT_NAME_MAP[raw_upper]
    
    # Fallback to Title Case
    return str(raw_type).replace("_", " ").title()


def validate_barcode_checksum(barcode_type: str, data: str) -> Tuple[str, Optional[str]]:
    """Validate checksum for supported 1D barcode formats.
    
    Returns (status, details) where status is one of:
      - "Valid"
      - "Invalid"
      - "Not Available"
    """
    if not data or not barcode_type:
        return "Not Available", "No data to validate"

    clean_type = normalize_barcode_type(barcode_type)
    cleaned_data = data.strip()

    # 1. EAN-13 (13 digits, Modulo 10)
    if clean_type == "EAN-13":
        if not cleaned_data.isdigit() or len(cleaned_data) != 13:
            return "Invalid", f"EAN-13 expects 13 digits, got {len(cleaned_data)}"
        digits = [int(c) for c in cleaned_data]
        s = sum(digits[i] for i in range(0, 12, 2)) + sum(digits[i] * 3 for i in range(1, 12, 2))
        expected = (10 - (s % 10)) % 10
        actual = digits[12]
        if expected == actual:
            return "Valid", f"Modulo 10 check digit valid ({actual})"
        return "Invalid", f"Modulo 10 check digit mismatch (Expected {expected}, got {actual})"

    # 2. EAN-8 (8 digits, Modulo 10)
    if clean_type == "EAN-8":
        if not cleaned_data.isdigit() or len(cleaned_data) != 8:
            return "Invalid", f"EAN-8 expects 8 digits, got {len(cleaned_data)}"
        digits = [int(c) for c in cleaned_data]
        s = sum(digits[i] * 3 for i in range(0, 7, 2)) + sum(digits[i] for i in range(1, 7, 2))
        expected = (10 - (s % 10)) % 10
        actual = digits[7]
        if expected == actual:
            return "Valid", f"Modulo 10 check digit valid ({actual})"
        return "Invalid", f"Modulo 10 check digit mismatch (Expected {expected}, got {actual})"

    # 3. UPC-A (12 digits, Modulo 10)
    if clean_type == "UPC-A":
        if not cleaned_data.isdigit() or len(cleaned_data) != 12:
            return "Invalid", f"UPC-A expects 12 digits, got {len(cleaned_data)}"
        digits = [int(c) for c in cleaned_data]
        s = sum(digits[i] * 3 for i in range(0, 11, 2)) + sum(digits[i] for i in range(1, 11, 2))
        expected = (10 - (s % 10)) % 10
        actual = digits[11]
        if expected == actual:
            return "Valid", f"Modulo 10 check digit valid ({actual})"
        return "Invalid", f"Modulo 10 check digit mismatch (Expected {expected}, got {actual})"

    # 4. UPC-E (6, 7, or 8 digits)
    if clean_type == "UPC-E":
        if not cleaned_data.isdigit() or len(cleaned_data) not in (6, 7, 8):
            return "Invalid", f"UPC-E expects 6-8 digits, got {len(cleaned_data)}"
        if len(cleaned_data) == 8:
            ns = cleaned_data[0]
            body = cleaned_data[1:7]
            cd = int(cleaned_data[7])
            d1, d2, d3, d4, d5, d6 = body
            if d6 in ("0", "1", "2"):
                upca_body = ns + d1 + d2 + d6 + "0000" + d3 + d4 + d5
            elif d6 == "3":
                upca_body = ns + d1 + d2 + d3 + "00000" + d4 + d5
            elif d6 == "4":
                upca_body = ns + d1 + d2 + d3 + d4 + "00000" + d5
            else:
                upca_body = ns + d1 + d2 + d3 + d4 + d5 + "0000" + d6

            digits = [int(c) for c in upca_body]
            s = sum(digits[i] * 3 for i in range(0, 11, 2)) + sum(digits[i] for i in range(1, 11, 2))
            expected = (10 - (s % 10)) % 10
            if expected == cd:
                return "Valid", f"UPC-E check digit valid ({cd})"
            return "Invalid", f"UPC-E check digit mismatch (Expected {expected}, got {cd})"
        return "Valid", "UPC-E structural format valid"

    # 5. ITF-14 (14 digits, Modulo 10)
    if clean_type in ("ITF-14", "ITF") and len(cleaned_data) == 14 and cleaned_data.isdigit():
        digits = [int(c) for c in cleaned_data]
        s = sum(digits[i] * 3 for i in range(0, 13, 2)) + sum(digits[i] for i in range(1, 13, 2))
        expected = (10 - (s % 10)) % 10
        actual = digits[13]
        if expected == actual:
            return "Valid", f"ITF-14 check digit valid ({actual})"
        return "Invalid", f"ITF-14 check digit mismatch (Expected {expected}, got {actual})"

    # Formats without fixed length / standardized single check digit
    return "Not Available", f"Checksum not required for {clean_type}"


def setup_logging(log_dir: Optional[Path] = None) -> logging.Logger:
    """Configure structured application logging with rotating file handler and console output."""
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent / "logs"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    logger = logging.getLogger("BarcodeReader")
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if logger was already initialized
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s.%(funcName)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Rotating file handler (5 MB max size, 3 backup files)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "BarcodeReader") -> logging.Logger:
    """Get an application logger instance."""
    return logging.getLogger(name)


def copy_to_clipboard(text: str, root=None) -> bool:
    """Copy text to system clipboard safely."""
    if tk is None:
        # Tkinter not available; cannot copy to clipboard
        return False
    try:
        if root is not None:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            return True
        else:
            temp_root = tk.Tk()
            temp_root.withdraw()
            temp_root.clipboard_clear()
            temp_root.clipboard_append(text)
            temp_root.update()
            temp_root.destroy()
            return True
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to copy to clipboard: {e}")
        return False

