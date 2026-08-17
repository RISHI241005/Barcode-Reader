"""Standalone Database Setup and Migration Utility for Barcode Reader (Part 7)."""

import sys
from src.database import DatabaseManager


def run_setup():
    """Execute complete database initialization and migration."""
    print("=" * 60)
    print("  Barcode Reader — MySQL Database Setup Wizard (v1.0.0)")
    print("=" * 60)

    db_manager = DatabaseManager()
    cfg = db_manager.config

    print(f"\nTarget Database Configuration:")
    print(f"  • Host:     {cfg.host}")
    print(f"  • Port:     {cfg.port}")
    print(f"  • Database: {cfg.database}")
    print(f"  • User:     {cfg.user}")

    print("\nConnecting to MySQL Server...")
    ok, msg = db_manager.test_connection(include_database=False)
    if not ok:
        print(f"❌ Connection failed: {msg}")
        print("\nPlease ensure MySQL Server is running and credentials in .env are correct.")
        sys.exit(1)

    print("✓ MySQL connection established successfully.")

    print("\nInitializing database and applying safe table migrations...")
    init_ok, init_msg = db_manager.initialize_database()

    if init_ok:
        print("✓ Database verified/created.")
        print("✓ Table `users` ready.")
        print("✓ Table `barcode_scans` ready (with user_id scoping).")
        print("✓ Table `products` ready.")
        print("✓ Table `audit_logs` ready.")
        print("\n" + "=" * 60)
        print("🎉 Database setup completed successfully! You can now launch app.py.")
        print("=" * 60)
    else:
        print(f"❌ Database initialization error: {init_msg}")
        sys.exit(1)


if __name__ == "__main__":
    run_setup()
