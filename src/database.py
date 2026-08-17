"""Database connection manager, initialization, and health checks for MySQL."""

import os
from pathlib import Path
from typing import Optional, Tuple
import mysql.connector
from mysql.connector import Error as MySQLError
from dotenv import load_dotenv

from src.utils import get_logger

logger = get_logger()

# Locate project root and load .env file
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class DatabaseManager:
    """Manages MySQL database connections, table creation, and connection health."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = int(port or os.getenv("DB_PORT", "3306"))
        self.database = database or os.getenv("DB_NAME", "barcode_reader")
        self.user = user or os.getenv("DB_USER", "root")
        self.password = password if password is not None else os.getenv("DB_PASSWORD", "")

    def reload_config(self):
        """Reload configuration from .env file."""
        if ENV_PATH.exists():
            load_dotenv(ENV_PATH, override=True)
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.database = os.getenv("DB_NAME", "barcode_reader")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")

    def get_connection(self, include_database: bool = True):
        """Obtain a new connection to MySQL server with a strict timeout."""
        config = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "connect_timeout": 3,
            "autocommit": False,
        }
        if include_database and self.database:
            config["database"] = self.database

        return mysql.connector.connect(**config)

    def test_connection(self) -> Tuple[bool, str]:
        """Test whether the MySQL database is reachable and configured correctly."""
        try:
            conn = self.get_connection(include_database=False)
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True, "Connected to MySQL server."
        except MySQLError as e:
            logger.warning(f"MySQL connection test failed: {e.msg} (Error Code: {e.errno})")
            return False, f"MySQL connection failed: {e.msg}"
        except Exception as e:
            logger.warning(f"Unexpected connection error: {e}")
            return False, f"Connection error: {str(e)}"

    def initialize_database(self) -> Tuple[bool, str]:
        """Create the database and barcode_scans table if they do not already exist."""
        try:
            # 1. Connect to MySQL server without database to check/create DB
            server_conn = self.get_connection(include_database=False)
            server_cursor = server_conn.cursor()
            
            # Create database if not exists (using parameterized or safe identifier)
            safe_db_name = "".join(c for c in self.database if c.isalnum() or c == "_")
            create_db_query = (
                f"CREATE DATABASE IF NOT EXISTS `{safe_db_name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            server_cursor.execute(create_db_query)
            server_conn.commit()
            server_cursor.close()
            server_conn.close()
            logger.info(f"Database `{safe_db_name}` verified or created successfully.")

            # 2. Connect to the database and create table if not exists
            db_conn = self.get_connection(include_database=True)
            db_cursor = db_conn.cursor()

            create_table_query = """
            CREATE TABLE IF NOT EXISTS barcode_scans (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                barcode_type VARCHAR(50) NOT NULL,
                barcode_data TEXT NOT NULL,
                image_name VARCHAR(255),
                scan_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                validation_status VARCHAR(30) DEFAULT 'Not Available',
                x_position INT DEFAULT 0,
                y_position INT DEFAULT 0,
                width INT DEFAULT 0,
                height INT DEFAULT 0,
                processing_method VARCHAR(100) DEFAULT 'Original Image',
                processing_time_ms DOUBLE DEFAULT 0.0,
                source VARCHAR(20) DEFAULT 'image',
                INDEX idx_barcode_type (barcode_type),
                INDEX idx_scan_date (scan_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            db_cursor.execute(create_table_query)

            # Safe migration: ensure 'source' column exists in barcode_scans
            try:
                db_cursor.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'barcode_scans' AND COLUMN_NAME = 'source';",
                    (safe_db_name,),
                )
                if not db_cursor.fetchone():
                    db_cursor.execute(
                        "ALTER TABLE barcode_scans ADD COLUMN source VARCHAR(20) DEFAULT 'image';"
                    )
                    logger.info("Migrated table `barcode_scans`: added `source` column.")
            except Exception as mig_err:
                logger.debug(f"Source column migration notice: {mig_err}")

            # Create products table for local caching and product management
            create_products_query = """
            CREATE TABLE IF NOT EXISTS products (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                barcode VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255),
                brand VARCHAR(255),
                category VARCHAR(255),
                description TEXT,
                image_url TEXT,
                quantity VARCHAR(100),
                ingredients TEXT,
                allergens TEXT,
                source VARCHAR(100) DEFAULT 'Product API',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_product_barcode (barcode),
                INDEX idx_product_name (name),
                INDEX idx_product_brand (brand)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            db_cursor.execute(create_products_query)

            # Create users table for authentication and user management
            create_users_query = """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'USER',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                last_login DATETIME NULL,
                INDEX idx_user_username (username),
                INDEX idx_user_email (email),
                INDEX idx_user_role (role)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            db_cursor.execute(create_users_query)

            # Safe migration: ensure 'user_id' column exists in barcode_scans
            try:
                db_cursor.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'barcode_scans' AND COLUMN_NAME = 'user_id';",
                    (safe_db_name,),
                )
                if not db_cursor.fetchone():
                    db_cursor.execute(
                        "ALTER TABLE barcode_scans ADD COLUMN user_id BIGINT NULL, "
                        "ADD INDEX idx_user_id (user_id);"
                    )
                    logger.info("Migrated table `barcode_scans`: added `user_id` column and index.")
            except Exception as mig_err:
                logger.debug(f"User ID column migration notice: {mig_err}")

            # Create audit_logs table for administrative and security auditing
            create_audit_query = """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NULL,
                username VARCHAR(100) NULL,
                action VARCHAR(100) NOT NULL,
                target_type VARCHAR(50) NULL,
                target_id VARCHAR(100) NULL,
                description TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_audit_action (action),
                INDEX idx_audit_user_id (user_id),
                INDEX idx_audit_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            db_cursor.execute(create_audit_query)

            db_conn.commit()
            db_cursor.close()
            db_conn.close()
            logger.info("Tables `users`, `barcode_scans`, `products`, and `audit_logs` verified successfully.")
            return True, "Database and tables initialized successfully."

        except MySQLError as e:
            err_msg = f"Database initialization failed: {e.msg} (Code: {e.errno})"
            logger.error(err_msg)
            return False, err_msg
        except Exception as e:
            err_msg = f"Unexpected initialization error: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
