"""Standalone Database Setup and Migration Utility for Barcode Reader (Part 7)."""

import sys
from src.database import DatabaseManager


def run_setup():
    """Execute complete database initialization and migration."""
    print("=" * 60)
    print("  Barcode Reader — MySQL Database Setup Wizard (v1.0.0)")
    print("=" * 60)

    db_manager = DatabaseManager()

    print(f"\nTarget Database Configuration:")
    print(f"  • Host:     {db_manager.host}")
    print(f"  • Port:     {db_manager.port}")
    print(f"  • Database: {db_manager.database}")
    print(f"  • User:     {db_manager.user}")

    print("\nConnecting to MySQL Server...")
    ok, msg = db_manager.test_connection()
    if not ok:
        print(f"[X] Connection failed: {msg}")
        print("\nPlease ensure MySQL Server is running and credentials in .env are correct.")
        sys.exit(1)

    print("[OK] MySQL connection established successfully.")

    print("\nInitializing database and applying safe table migrations...")
    init_ok, init_msg = db_manager.initialize_database()

    if init_ok:
        print("[OK] Database verified/created.")
        print("[OK] Table `users` ready.")
        print("[OK] Table `barcode_scans` ready (with user_id scoping).")
        print("[OK] Table `products` ready.")
        print("[OK] Table `audit_logs` ready.")
        print("\n" + "=" * 60)
        print(">> Database setup completed successfully! You can now launch app.py.")
        print("=" * 60)
    else:
        print(f"[X] Database initialization error: {init_msg}")
        sys.exit(1)


if __name__ == "__main__":
    run_setup()
