"""
Module: logging
Layer: common
Purpose: Structured logging utility — all layers use get_logger(), never print().
    Emits JSON lines with timestamp, level, name, message, and optional extra fields.
Dependencies: logging, json, datetime
Used by: all layers
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Logging formatter that emits one JSON object per log record.

    Output fields:
        timestamp: ISO-8601 UTC string.
        level: Log level name (e.g. "INFO").
        name: Logger name (module path).
        message: Formatted log message.
        extra: Dict of any additional attributes attached to the record.
    """

    _RESERVED_ATTRS: frozenset[str] = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
    })

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a JSON string.

        Args:
            record: The log record to format.
        Returns:
            A single-line JSON string.
        """
        record.message = record.getMessage()
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        extra = self._extract_extra(record)
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "name": record.name,
            "message": record.message,
        }
        if extra:
            payload["extra"] = extra
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract non-standard attributes from a log record.

        Args:
            record: The log record to inspect.
        Returns:
            Dict of extra attributes not part of the standard LogRecord fields.
        """
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._RESERVED_ATTRS
        }


def get_logger(name: str) -> logging.Logger:
    """Return a structured JSON logger for the given module name.

    Args:
        name: Logger name, conventionally ``__name__`` of the calling module.
    Returns:
        A configured :class:`logging.Logger` that emits JSON lines to stderr.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
