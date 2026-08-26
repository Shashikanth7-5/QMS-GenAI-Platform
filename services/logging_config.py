"""Central logging setup.

Prefer:
    from services.logging_config import get_logger
    log = get_logger(__name__)
    log.info("audit.entry.saved", extra={"capa_id": capa_id})

In prod, LOG_FORMAT=json emits one JSON object per line so log
aggregators (Splunk / ELK / CloudWatch) can index every field.
In dev, LOG_FORMAT=text emits a human-readable line.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import sys
import threading
from typing import Any, Mapping

_configured_lock = threading.Lock()
_configured = False


class _JsonFormatter(logging.Formatter):
    """Emit each record as a single JSON object per line."""

    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Any custom fields passed via `extra=` land as record attributes.
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging() -> None:
    """Idempotent: safe to call from app factory and Celery bootstrap."""
    global _configured
    with _configured_lock:
        if _configured:
            return

        from config import LOG_FORMAT, LOG_LEVEL

        handler = logging.StreamHandler(stream=sys.stdout)
        if LOG_FORMAT == "json":
            handler.setFormatter(_JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        root = logging.getLogger()
        # Remove any pre-existing handlers (Flask / gunicorn add their own).
        for existing in list(root.handlers):
            root.removeHandler(existing)
        root.addHandler(handler)
        root.setLevel(LOG_LEVEL if LOG_LEVEL in logging._nameToLevel else "INFO")

        # Silence noisy third-party libs unless explicitly asked.
        for noisy in ("httpx", "httpcore", "urllib3", "chromadb"):
            logging.getLogger(noisy).setLevel(os.getenv("LOG_LEVEL_THIRD_PARTY", "WARNING"))

        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Preferred entry point. Configures logging on first call."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


def bind(logger: logging.Logger, **fields: Any) -> logging.LoggerAdapter:
    """Attach persistent structured fields for downstream log lines."""
    return logging.LoggerAdapter(logger, _MergingContext(fields))


class _MergingContext(dict):
    """LoggerAdapter contexts are merged into `extra` on every emit."""

    def __init__(self, base: Mapping[str, Any]):
        super().__init__(base)
