# config/logging_config.py
"""
Sentinel-X | Structured Logging Configuration
Consistent log format across all phases and agents.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = False,
    log_file: Path | None = None,
) -> None:
    """
    Configure root logger for the entire Sentinel-X package.
    Call once at application entry point.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout)
    ]

    if log_to_file and log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )

    # Suppress noisy third-party loggers
    for noisy in ["httpx", "httpcore", "chromadb", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Use __name__ in every module."""
    return logging.getLogger(name)