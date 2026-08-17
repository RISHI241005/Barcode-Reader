"""Centralized application configuration and environment validation (Part 7)."""

import os
from pathlib import Path
from typing import List, Tuple
from dotenv import load_dotenv

# Load environment configuration from .env file
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

# Application Metadata
APP_NAME = "Barcode Reader"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Rishi Gupta"
APP_DESCRIPTION = (
    "Enterprise Multi-User Barcode & QR Code Intelligence Platform with Live Camera Scanning, "
    "Product Intelligence, MySQL Storage, Analytics, and Role-Based Access Control."
)

# MySQL Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "barcode_reader")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Authentication & Session Configuration
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "5"))

# External Product API Configuration
PRODUCT_API_BASE_URL = os.getenv(
    "PRODUCT_API_BASE_URL", "https://world.openfoodfacts.org/api/v2/product/"
)
PRODUCT_API_TIMEOUT = int(os.getenv("PRODUCT_API_TIMEOUT", "5"))


def validate_environment() -> Tuple[bool, List[str]]:
    """Validate runtime environment and configuration parameters.
    
    Returns:
        (is_valid, list_of_warning_or_error_messages)
    """
    notices = []

    # Check for empty DB password (common warning on production setups)
    if not DB_PASSWORD:
        notices.append("DB_PASSWORD is empty or unset; using default root/empty password.")

    if SESSION_TIMEOUT_MINUTES < 1:
        notices.append("SESSION_TIMEOUT_MINUTES is set to less than 1 minute; defaulting to 30.")

    if PRODUCT_API_TIMEOUT < 1:
        notices.append("PRODUCT_API_TIMEOUT is set to less than 1 second; defaulting to 5.")

    return True, notices
