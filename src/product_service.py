"""External Product API service, provider abstraction, and response normalizer (Part 5)."""

from abc import ABC, abstractmethod
import os
from typing import Optional, Tuple
import requests

from src.models import Product
from src.product_repository import ProductRepository
from src.utils import get_logger

logger = get_logger()

# Configurable API defaults
DEFAULT_API_BASE_URL = os.getenv(
    "PRODUCT_API_BASE_URL", "https://world.openfoodfacts.org/api/v2/product/"
)
DEFAULT_API_TIMEOUT = int(os.getenv("PRODUCT_API_TIMEOUT", "5"))


class ProductProvider(ABC):
    """Abstract interface for external barcode/product information providers."""

    @abstractmethod
    def lookup(self, barcode: str, timeout: int = 5) -> Tuple[Optional[Product], Optional[str]]:
        """Query product data by barcode and return (Product, error_message)."""
        pass


class OpenFoodFactsProvider(ProductProvider):
    """Provider implementation for Open Food Facts & Open Products Facts REST API."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_API_BASE_URL).rstrip("/") + "/"
        self.headers = {
            "User-Agent": "BarcodeReaderDesktop/1.0 (Desktop App; Python; +https://github.com/barcode-reader)"
        }

    def lookup(self, barcode: str, timeout: int = 5) -> Tuple[Optional[Product], Optional[str]]:
        """Fetch and normalize product data from Open Food Facts API."""
        clean_barcode = "".join(c for c in barcode if c.isalnum())
        if not clean_barcode:
            return None, "Invalid barcode identifier."

        endpoint = f"{self.base_url}{clean_barcode}.json"
        logger.info(f"Issuing external product lookup for barcode: {clean_barcode}")

        try:
            resp = requests.get(endpoint, headers=self.headers, timeout=timeout)
            
            if resp.status_code == 404:
                return None, "Product not found in product database."
            elif resp.status_code == 429:
                return None, "Product service rate limit reached. Please try again in a few moments."
            elif resp.status_code != 200:
                return None, f"Product service returned HTTP error {resp.status_code}."

            data = resp.json()
            if not data or data.get("status") == 0 or "product" not in data:
                return None, "Product not found in product database."

            p_data = data["product"]

            # Normalize fields with safe fallbacks
            name = (
                p_data.get("product_name")
                or p_data.get("product_name_en")
                or p_data.get("generic_name")
                or "Not available"
            )
            brand = p_data.get("brands") or p_data.get("brand_owner") or "Not available"
            category = p_data.get("categories") or p_data.get("main_category") or "Not available"
            # Keep first 3 category tokens for clean display if comma-separated
            if category != "Not available" and "," in category:
                category = ", ".join([c.strip() for c in category.split(",")[:3]])

            description = (
                p_data.get("generic_name_en")
                or p_data.get("generic_name")
                or p_data.get("ingredients_text_with_allergens")
                or "Not available"
            )
            image_url = p_data.get("image_front_url") or p_data.get("image_url") or None
            quantity = p_data.get("quantity") or p_data.get("serving_size") or "Not available"
            ingredients = (
                p_data.get("ingredients_text_en")
                or p_data.get("ingredients_text")
                or "Not available"
            )
            allergens = p_data.get("allergens") or p_data.get("allergens_tags") or "Not available"
            if isinstance(allergens, list):
                allergens = ", ".join(allergens) if allergens else "Not available"

            product = Product(
                barcode=clean_barcode,
                name=name,
                brand=brand,
                category=category,
                description=description,
                image_url=image_url,
                quantity=quantity,
                ingredients=ingredients,
                allergens=allergens,
                source="Open Food Facts",
            )
            return product, None

        except requests.exceptions.Timeout:
            logger.warning(f"Product API request timed out after {timeout}s for barcode {clean_barcode}")
            return None, "Product service request timed out. Please check your network connection."
        except requests.exceptions.ConnectionError:
            logger.warning("Product API connection failed (offline or DNS error).")
            return None, "Unable to connect to product service. Please check your internet connection."
        except Exception as e:
            logger.exception(f"Unexpected error in product lookup: {e}")
            return None, f"Product service error: {str(e)}"


class ProductService:
    """Coordinates product lookups between local MySQL cache and external Product APIs."""

    def __init__(
        self,
        repository: Optional[ProductRepository] = None,
        provider: Optional[ProductProvider] = None,
        timeout: int = DEFAULT_API_TIMEOUT,
    ):
        self.repository = repository or ProductRepository()
        self.provider = provider or OpenFoodFactsProvider()
        self.timeout = timeout

    def lookup_product(
        self, barcode: str, force_refresh: bool = False
    ) -> Tuple[Optional[Product], str, bool]:
        """Look up product by barcode.
        
        Returns:
            (Product, status_message, is_from_cache)
        """
        clean_barcode = "".join(c for c in barcode if c.isalnum())
        if not clean_barcode:
            return None, "Invalid barcode value.", False

        # 1. Check local MySQL cache first (if not forcing fresh API fetch)
        if not force_refresh:
            cached = self.repository.get_product_by_barcode(clean_barcode)
            if cached:
                logger.info(f"Product cache hit for barcode {clean_barcode}")
                return cached, "Product loaded from local cache.", True

        # 2. Query external product API
        product, err = self.provider.lookup(clean_barcode, timeout=self.timeout)
        if product:
            # 3. Cache product in MySQL for future offline/instant access
            self.repository.save_or_update_product(product)
            return product, "Product retrieved from external database.", False

        # If API failed or offline, try falling back to local cache even if force_refresh was requested
        if force_refresh:
            cached = self.repository.get_product_by_barcode(clean_barcode)
            if cached:
                return cached, f"Loaded from local cache (API unavailable: {err})", True

        return None, err or "Product not found.", False

    def test_api_connection(self) -> Tuple[bool, str]:
        """Check if external product API endpoint is reachable."""
        try:
            resp = requests.head(DEFAULT_API_BASE_URL, timeout=3)
            if resp.status_code in (200, 301, 302, 404):
                return True, "Product API available."
            return False, f"API returned status {resp.status_code}."
        except Exception:
            return False, "Product API offline or unreachable."
