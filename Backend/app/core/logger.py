import logging
import sys
import os
from app.core.config import Settings


def setup_logger(name: str = "app"):
    logger = logging.getLogger(name)
    logger.setLevel(Settings.LOG_LEVEL)

    # Check if handlers are already added to avoid duplicate logs
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(Settings.LOG_LEVEL)

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

        # File Handler (Optional: create logs directory if it doesn't exist)
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(
            os.path.join(log_dir, "app.log"), encoding="utf-8"
        )
        file_handler.setLevel(Settings.LOG_LEVEL)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
