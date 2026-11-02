
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents = True, exist_ok = True)

LOG_FORMAT = (
    "%(asctime)s | %(name)-28s | "
    "%(levelname)-7s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(  name: str,  level: int = logging.INFO,) -> logging.Logger:
    """Return a named logger with consistent console formatting."""

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers: # check if handlers already exist to avoid duplicate logs
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(  LOG_FORMAT, datefmt = DATE_FORMAT, )

        file_handler = RotatingFileHandler(
                LOG_DIR / "contentalchemy.log",
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3,
                encoding="utf-8",
            )
        file_handler.setFormatter(formatter) #set the formatter for the file handler
        handler.setFormatter(formatter) #set the formatter for the console handler

        logger.addHandler(handler) # add the console handler to the logger
        logger.addHandler(file_handler) #add the file handler to the logger

    return logger






