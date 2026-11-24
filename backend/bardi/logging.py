"""Structured single-line JSON logger with automatic secret redaction (INV-101)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

REDACTED_LITERAL = "<REDACTED>"
SENSITIVE_KEY_SUBSTRINGS = (
    "local_key",
    "access_token",
    "x-bardi-token",
    "token",
    "secret",
    "password",
    "authorization",
)


def is_sensitive_key(key: str) -> bool:
    """Return True if a field name represents a credential or secret."""
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_SUBSTRINGS)


def redact_mapping(payload: Any) -> Any:
    """Recursively redact sensitive keys in dictionaries and sequences."""
    if isinstance(payload, dict):
        return {
            str(k): (REDACTED_LITERAL if is_sensitive_key(str(k)) else redact_mapping(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list | tuple):
        return [redact_mapping(item) for item in payload]
    return payload


class RedactingJsonFormatter(logging.Formatter):
    """Formats log records as single-line structured JSON with credential redaction."""

    _STANDARD_ATTRS = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._STANDARD_ATTRS or key.startswith("_"):
                continue
            if is_sensitive_key(key):
                base[key] = REDACTED_LITERAL
            else:
                base[key] = redact_mapping(value)
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=True)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the root 'bardi' logger with RedactingJsonFormatter."""
    logger = logging.getLogger("bardi")
    logger.setLevel(level)
    logger.propagate = False
    if not any(
        isinstance(getattr(h, "formatter", None), RedactingJsonFormatter)
        for h in logger.handlers
    ):
        logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(RedactingJsonFormatter())
        logger.addHandler(handler)
    return logger


def get_logger(name: str = "bardi") -> logging.Logger:
    """Return a configured child logger under the 'bardi' namespace."""
    configure_logging()
    return logging.getLogger(name)
