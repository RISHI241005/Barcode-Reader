"""Repository layer for local MySQL product caching and product catalog management (Part 5)."""

from typing import List, Optional, Tuple
from mysql.connector import Error as MySQLError

from src.database import DatabaseManager
from src.models import Product
from src.utils import get_logger

logger = get_logger()


class ProductRepository:
    """Repository handling CRUD operations and queries for cached products in MySQL."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()

    def get_product_by_barcode(self, barcode: str) -> Optional[Product]:
        """Retrieve a product by its exact barcode identifier from MySQL cache."""
        if not barcode:
            return None

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            sql = """
            SELECT id, barcode, name, brand, category, description,
                   image_url, quantity, ingredients, allergens, source,
                   created_at, updated_at
            FROM products
            WHERE barcode = %s
            LIMIT 1;
            """
            cursor.execute(sql, (barcode.strip(),))
            row = cursor.fetchone()
            if not row:
                return None

            return Product(
                id=row["id"],
                barcode=row["barcode"],
                name=row["name"] or "Not available",
                brand=row["brand"] or "Not available",
                category=row["category"] or "Not available",
                description=row["description"] or "Not available",
                image_url=row["image_url"],
                quantity=row["quantity"] or "Not available",
                ingredients=row["ingredients"] or "Not available",
                allergens=row["allergens"] or "Not available",
                source=row["source"] or "Product API",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        except MySQLError as e:
            logger.error(f"Database error retrieving product for barcode {barcode}: {e.msg}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving product: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_or_update_product(self, product: Product) -> Tuple[bool, Optional[int], Optional[str]]:
        """Insert or update a product record in MySQL cache using parameterized upsert."""
        if not product or not product.barcode:
            return False, None, "Invalid product or missing barcode."

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            upsert_sql = """
            INSERT INTO products (
                barcode, name, brand, category, description,
                image_url, quantity, ingredients, allergens, source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                brand = VALUES(brand),
                category = VALUES(category),
                description = VALUES(description),
                image_url = VALUES(image_url),
                quantity = VALUES(quantity),
                ingredients = VALUES(ingredients),
                allergens = VALUES(allergens),
                source = VALUES(source),
                updated_at = CURRENT_TIMESTAMP;
            """
            params = (
                product.barcode.strip(),
                product.name,
                product.brand,
                product.category,
                product.description,
                product.image_url,
                product.quantity,
                product.ingredients,
                product.allergens,
                product.source or "Product API",
            )
            cursor.execute(upsert_sql, params)
            inserted_id = cursor.lastrowid
            conn.commit()

            logger.info(f"Product `{product.barcode}` ('{product.name}') cached successfully in MySQL.")
            return True, inserted_id, None

        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error caching product: {e.msg}"
            logger.error(err_msg)
            return False, None, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to save product: {str(e)}"
            logger.error(err_msg)
            return False, None, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_product(self, barcode: str) -> Tuple[bool, Optional[str]]:
        """Delete a cached product from MySQL without deleting scan history."""
        if not barcode:
            return False, "Missing barcode identifier."

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products WHERE barcode = %s;", (barcode.strip(),))
            conn.commit()
            logger.info(f"Deleted cached product for barcode: {barcode}")
            return True, None
        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error deleting product `{barcode}`: {e.msg}"
            logger.error(err_msg)
            return False, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to delete product: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def search_products(
        self,
        search_term: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Tuple[List[Product], int]:
        """Search products by barcode, name, brand, or category with pagination."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            where_clause = ""
            params = []

            if search_term and search_term.strip():
                term = f"%{search_term.strip()}%"
                where_clause = (
                    "WHERE (barcode LIKE %s OR name LIKE %s OR brand LIKE %s OR category LIKE %s)"
                )
                params = [term, term, term, term]

            count_sql = f"SELECT COUNT(*) as total FROM products {where_clause};"
            cursor.execute(count_sql, tuple(params))
            count_res = cursor.fetchone()
            total_count = count_res["total"] if count_res else 0

            offset = max(0, (page - 1) * page_size)
            query_sql = f"""
            SELECT id, barcode, name, brand, category, description,
                   image_url, quantity, ingredients, allergens, source,
                   created_at, updated_at
            FROM products
            {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s OFFSET %s;
            """
            query_params = list(params) + [page_size, offset]
            cursor.execute(query_sql, tuple(query_params))
            rows = cursor.fetchall()

            products = [
                Product(
                    id=row["id"],
                    barcode=row["barcode"],
                    name=row["name"] or "Not available",
                    brand=row["brand"] or "Not available",
                    category=row["category"] or "Not available",
                    description=row["description"] or "Not available",
                    image_url=row["image_url"],
                    quantity=row["quantity"] or "Not available",
                    ingredients=row["ingredients"] or "Not available",
                    allergens=row["allergens"] or "Not available",
                    source=row["source"] or "Product API",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

            return products, total_count

        except MySQLError as e:
            logger.error(f"Database error searching products: {e.msg}")
            return [], 0
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return [], 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def count_products(self) -> int:
        """Return total number of cached products."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM products;")
            res = cursor.fetchone()
            return res[0] if res else 0
        except Exception as e:
            logger.error(f"Error counting products: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
