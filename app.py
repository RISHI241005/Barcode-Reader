"""Application entry point for Barcode Reader."""

import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Setup Windows DPI awareness for crisp UI rendering
if sys.platform == "win32":
    try:
        import ctypes
        # Set PROCESS_SYSTEM_DPI_AWARE (1) or PROCESS_PER_MONITOR_DPI_AWARE (2)
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from src.utils import setup_logging
from src.config import validate_environment, APP_NAME, APP_VERSION
from src.gui import BarcodeReaderApp


def main():
    """Initialize logging, validate configuration, and launch Barcode Reader."""
    # Ensure logs directory exists
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Initialize application logging
    logger = setup_logging(logs_dir)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on {sys.platform}...")

    # Validate environment
    _, env_notices = validate_environment()
    for notice in env_notices:
        logger.info(f"Configuration notice: {notice}")

    try:
        app = BarcodeReaderApp()

        # Set application window icon if available
        icon_path = PROJECT_ROOT / "assets" / "barcode_reader.ico"
        if icon_path.exists():
            try:
                app.iconbitmap(str(icon_path))
            except Exception as icon_err:
                logger.debug(f"Could not set window icon: {icon_err}")

        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Application closed by user.")
    except Exception as e:
        logger.critical(f"Fatal unhandled exception in application: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
