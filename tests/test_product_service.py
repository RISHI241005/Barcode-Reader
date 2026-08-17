"""Unit tests for Product model, OpenFoodFactsProvider, and ProductService (Part 5)."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from src.models import Product
from src.product_service import ProductService, OpenFoodFactsProvider


def test_product_model_properties_and_serialization():
    """Test 1: Product dataclass fields, fallback defaults, and dictionary serialization."""
    prod = Product(
        barcode="8901234567890",
        name="Nutritional Biscuit",
        brand="Britannia",
        category="Snacks, Biscuits",
        quantity="250 g",
        ingredients="Wheat flour, Sugar, Palm oil",
        allergens="Gluten, Wheat",
        source="Open Food Facts",
    )

    assert prod.barcode == "8901234567890"
    assert prod.name == "Nutritional Biscuit"
    assert prod.brand == "Britannia"

    d = prod.to_dict()
    assert d["barcode"] == "8901234567890"
    assert d["name"] == "Nutritional Biscuit"
    assert d["source"] == "Open Food Facts"


def test_provider_product_found_normalization():
    """Test 2: OpenFoodFactsProvider correctly parses and normalizes API JSON responses."""
    provider = OpenFoodFactsProvider(base_url="https://fake.api/product/")

    mock_json_response = {
        "status": 1,
        "product": {
            "product_name": "Crunchy Hazelnut Spread",
            "brands": "Ferrero",
            "categories": "Breakfasts, Spreads, Sweet spreads",
            "quantity": "400 g",
            "ingredients_text_en": "Sugar, Palm oil, Hazelnuts 13%",
            "allergens": "Nuts, Milk, Soy",
            "image_front_url": "https://images.openfoodfacts.org/front.jpg",
        },
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json_response
        mock_get.return_value = mock_resp

        product, err = provider.lookup("8000500310427")

        assert err is None
        assert product is not None
        assert product.barcode == "8000500310427"
        assert product.name == "Crunchy Hazelnut Spread"
        assert product.brand == "Ferrero"
        assert product.quantity == "400 g"
        assert product.image_url == "https://images.openfoodfacts.org/front.jpg"


def test_provider_product_not_found():
    """Test 3: Provider handles 404 or status 0 as product not found."""
    provider = OpenFoodFactsProvider(base_url="https://fake.api/product/")

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        product, err = provider.lookup("9999999999999")
        assert product is None
        assert "not found" in err.lower()


def test_provider_timeout_and_network_error():
    """Test 4: Provider handles request timeouts and connection drops gracefully."""
    provider = OpenFoodFactsProvider(base_url="https://fake.api/product/")

    with patch("requests.get", side_effect=requests.exceptions.Timeout):
        product, err = provider.lookup("8901234567890", timeout=2)
        assert product is None
        assert "timed out" in err.lower()

    with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
        product, err = provider.lookup("8901234567890", timeout=2)
        assert product is None
        assert "unable to connect" in err.lower() or "connection" in err.lower()


def test_product_service_cache_hit_avoids_api_call():
    """Test 5: ProductService retrieves cached products from MySQL without making HTTP requests."""
    mock_repo = MagicMock()
    mock_provider = MagicMock()

    cached_prod = Product(
        barcode="8901234567890",
        name="Cached Organic Tea",
        brand="Twinings",
        source="Local Cache",
    )
    mock_repo.get_product_by_barcode.return_value = cached_prod

    service = ProductService(repository=mock_repo, provider=mock_provider)
    prod, msg, is_cached = service.lookup_product("8901234567890", force_refresh=False)

    assert is_cached is True
    assert prod.name == "Cached Organic Tea"
    # Verify external provider was NOT called!
    assert not mock_provider.lookup.called


def test_product_service_cache_miss_queries_api_and_saves():
    """Test 6: On cache miss, ProductService queries external API and saves result to MySQL."""
    mock_repo = MagicMock()
    mock_repo.get_product_by_barcode.return_value = None  # Cache miss

    api_prod = Product(
        barcode="1234567890128",
        name="Fresh Whole Milk",
        brand="DairyCo",
        source="Open Food Facts",
    )
    mock_provider = MagicMock()
    mock_provider.lookup.return_value = (api_prod, None)

    service = ProductService(repository=mock_repo, provider=mock_provider)
    prod, msg, is_cached = service.lookup_product("1234567890128", force_refresh=False)

    assert is_cached is False
    assert prod.name == "Fresh Whole Milk"
    # Verify API was called
    mock_provider.lookup.assert_called_with("1234567890128", timeout=service.timeout)
    # Verify product was cached into MySQL
    mock_repo.save_or_update_product.assert_called_with(api_prod)
