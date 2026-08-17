"""Unit tests for ProductRepository MySQL caching and CRUD operations (Part 5)."""

from unittest.mock import MagicMock
import pytest

from src.models import Product
from src.product_repository import ProductRepository


def test_product_repository_get_by_barcode():
    """Test 1: Retrieving a product by barcode executes parameterized query."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.return_value = {
        "id": 1,
        "barcode": "8901234567890",
        "name": "Natural Almond Butter",
        "brand": "NuttyCo",
        "category": "Spreads",
        "description": "100% roasted almonds",
        "image_url": None,
        "quantity": "300 g",
        "ingredients": "Almonds",
        "allergens": "Tree nuts",
        "source": "Open Food Facts",
        "created_at": "2026-08-17 10:00:00",
        "updated_at": "2026-08-17 10:00:00",
    }

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ProductRepository(mock_db)
    prod = repo.get_product_by_barcode("8901234567890")

    assert prod is not None
    assert prod.name == "Natural Almond Butter"
    assert prod.brand == "NuttyCo"


def test_product_repository_save_or_update():
    """Test 2: Saving product executes upsert SQL with commit."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.lastrowid = 5

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ProductRepository(mock_db)
    prod = Product(
        barcode="8901234567890",
        name="Natural Almond Butter",
        brand="NuttyCo",
        category="Spreads",
    )

    ok, pid, err = repo.save_or_update_product(prod)
    assert ok is True
    assert pid == 5
    assert mock_conn.commit.called


def test_product_repository_delete():
    """Test 3: Deleting product executes parameterized DELETE."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ProductRepository(mock_db)
    ok, err = repo.delete_product("8901234567890")

    assert ok is True
    assert err is None
    mock_cursor.execute.assert_called_with(
        "DELETE FROM products WHERE barcode = %s;", ("8901234567890",)
    )
    assert mock_conn.commit.called


def test_product_repository_search():
    """Test 4: Searching products builds parameterized query and returns matching items."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.return_value = {"total": 1}
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "barcode": "8901234567890",
            "name": "Natural Almond Butter",
            "brand": "NuttyCo",
            "category": "Spreads",
            "description": "100% roasted almonds",
            "image_url": None,
            "quantity": "300 g",
            "ingredients": "Almonds",
            "allergens": "Tree nuts",
            "source": "Open Food Facts",
            "created_at": "2026-08-17 10:00:00",
            "updated_at": "2026-08-17 10:00:00",
        }
    ]

    mock_db = MagicMock()
    mock_db.get_connection.return_value = mock_conn

    repo = ProductRepository(mock_db)
    products, total = repo.search_products(search_term="Almond")

    assert total == 1
    assert len(products) == 1
    assert products[0].name == "Natural Almond Butter"
