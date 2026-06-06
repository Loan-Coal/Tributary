"""
Module: logging
Layer: common
Purpose: Structured logging helper for Tributary.
Dependencies: logging
Used by: all layers
"""
import logging
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
