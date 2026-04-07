import logging
import os
import sys
from pathlib import Path

from app.core.config import Settings


LOG_DIR = Path(__file__).resolve().parents[3] / "logs"


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
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                LOG_DIR / "app.log", encoding="utf-8"
            )
            file_handler.setLevel(Settings.LOG_LEVEL)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # 测试/沙箱环境下日志落盘失败时降级为仅控制台输出，不阻塞应用启动
            pass

    return logger


logger = setup_logger()
