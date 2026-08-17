"""Data models for Barcode Reader application (Part 3)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Union


@dataclass
class ImageMetrics:
    """Quality and dimension metrics for an analyzed image."""

    width: int
    height: int
    channels: int
    resolution_mp: float
    brightness: float
    contrast: float
    blur_score: float
    is_low_resolution: bool = False
    is_low_contrast: bool = False
    is_blurry: bool = False
    warnings: List[str] = field(default_factory=list)

    @property
    def dimensions_str(self) -> str:
        """Formatted dimensions string e.g. '1920 × 1080'."""
        return f"{self.width} × {self.height}"


@dataclass
class BarcodeResult:
    """Represents a single decoded barcode or QR code with location and validation metadata."""

    barcode_type: str
    raw_type: str
    data: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    polygon: List[Tuple[int, int]] = field(default_factory=list)
    rotation: int = 0
    processing_method: str = "Original Image"
    validation_status: str = "Not Available"  # "Valid", "Invalid", "Not Available"
    validation_details: Optional[str] = None
    confidence: Optional[float] = None

    @property
    def bounding_box(self) -> Tuple[int, int, int, int]:
        """Return (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)

    @property
    def center(self) -> Tuple[float, float]:
        """Return center point (cx, cy) of bounding box."""
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def to_dict(self) -> dict:
        """Convert barcode result to dictionary representation."""
        return {
            "type": self.barcode_type,
            "raw_type": self.raw_type,
            "data": self.data,
            "bounding_box": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            },
            "polygon": self.polygon,
            "rotation": self.rotation,
            "processing_method": self.processing_method,
            "validation_status": self.validation_status,
            "validation_details": self.validation_details,
        }


@dataclass
class DetectionReport:
    """Represents the complete outcome of barcode detection on an image."""

    success: bool
    results: List[BarcodeResult] = field(default_factory=list)
    stage_used: str = "None"
    processing_time_ms: float = 0.0
    error_message: Optional[str] = None
    engine_used: str = "Unknown"
    image_metrics: Optional[ImageMetrics] = None
    stages_attempted: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Return the number of detected barcodes."""
        return len(self.results)


@dataclass
class ScanRecord:
    """Represents a persistent barcode scan record stored in MySQL."""

    id: Optional[int] = None
    barcode_type: str = "Unknown"
    barcode_data: str = ""
    image_name: Optional[str] = None
    scan_date: Optional[Union[datetime, str]] = None
    validation_status: str = "Not Available"
    x_position: int = 0
    y_position: int = 0
    width: int = 0
    height: int = 0
    processing_method: str = "Original Image"
    processing_time_ms: float = 0.0
    source: str = "image"  # "image" or "camera"
    user_id: Optional[int] = None
    username: Optional[str] = None

    @property
    def formatted_date(self) -> str:
        """Return human-readable formatted timestamp string."""
        if isinstance(self.scan_date, datetime):
            return self.scan_date.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(self.scan_date, str):
            return self.scan_date
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        """Convert ScanRecord to dictionary for serialization/export."""
        return {
            "id": self.id,
            "barcode_type": self.barcode_type,
            "barcode_data": self.barcode_data,
            "image_name": self.image_name or "",
            "scan_date": self.formatted_date,
            "validation_status": self.validation_status,
            "x_position": self.x_position,
            "y_position": self.y_position,
            "width": self.width,
            "height": self.height,
            "processing_method": self.processing_method,
            "processing_time_ms": self.processing_time_ms,
            "source": self.source,
            "user_id": self.user_id,
            "username": self.username or "Anonymous",
        }


@dataclass
class User:
    """Represents an authenticated user account with role-based permissions."""

    username: str
    email: str
    password_hash: str
    role: str = "USER"  # "USER" or "ADMIN"
    is_active: bool = True
    id: Optional[int] = None
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None
    last_login: Optional[Union[datetime, str]] = None

    @property
    def is_admin(self) -> bool:
        """Check whether the user possesses administrator privileges."""
        return self.role.upper() == "ADMIN"

    @property
    def formatted_created_at(self) -> str:
        """Return human-readable account creation date."""
        if isinstance(self.created_at, datetime):
            return self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(self.created_at, str):
            return self.created_at
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def formatted_last_login(self) -> str:
        """Return human-readable last login timestamp."""
        if isinstance(self.last_login, datetime):
            return self.last_login.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(self.last_login, str):
            return self.last_login
        return "Never"

    def to_dict(self) -> dict:
        """Convert User to dictionary representation (excludes password hash for safety)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.formatted_created_at,
            "last_login": self.formatted_last_login,
        }


@dataclass
class AuditLog:
    """Represents an administrative or security audit event recorded in MySQL."""

    action: str
    user_id: Optional[int] = None
    username: Optional[str] = "system"
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    description: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[Union[datetime, str]] = None

    @property
    def formatted_created_at(self) -> str:
        """Return human-readable timestamp of the audit entry."""
        if isinstance(self.created_at, datetime):
            return self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(self.created_at, str):
            return self.created_at
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        """Convert AuditLog to dictionary representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username or "system",
            "action": self.action,
            "target_type": self.target_type or "N/A",
            "target_id": self.target_id or "N/A",
            "description": self.description or "",
            "created_at": self.formatted_created_at,
        }


@dataclass
class Product:
    """Represents normalized product information retrieved from an external API or local MySQL cache."""

    barcode: str
    name: Optional[str] = "Not available"
    brand: Optional[str] = "Not available"
    category: Optional[str] = "Not available"
    description: Optional[str] = "Not available"
    image_url: Optional[str] = None
    quantity: Optional[str] = "Not available"
    ingredients: Optional[str] = "Not available"
    allergens: Optional[str] = "Not available"
    source: Optional[str] = "Product API"
    id: Optional[int] = None
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

    @property
    def formatted_updated_at(self) -> str:
        """Formatted last updated timestamp."""
        if isinstance(self.updated_at, datetime):
            return self.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(self.updated_at, str):
            return self.updated_at
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        """Convert Product to dictionary representation."""
        return {
            "id": self.id,
            "barcode": self.barcode,
            "name": self.name or "Not available",
            "brand": self.brand or "Not available",
            "category": self.category or "Not available",
            "description": self.description or "Not available",
            "image_url": self.image_url,
            "quantity": self.quantity or "Not available",
            "ingredients": self.ingredients or "Not available",
            "allergens": self.allergens or "Not available",
            "source": self.source or "Product API",
            "updated_at": self.formatted_updated_at,
        }

