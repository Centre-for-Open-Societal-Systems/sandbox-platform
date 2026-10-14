"""Logging setup.

Two channels, matching the reference stack's Winston configuration:

* stdout / rotating file  - operational logs
* ``sandbox_logs`` table  - structured application events
* ``user_action_logs``    - audit trail of who did what
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from typing import Any

from app.config.settings import settings

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s")
    )
    root.addHandler(console)

    os.makedirs(settings.LOG_DIR, exist_ok=True)
    rotating = logging.handlers.TimedRotatingFileHandler(
        os.path.join(settings.LOG_DIR, "oan-sandbox.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    rotating.setFormatter(_JsonFormatter())
    root.addHandler(rotating)

    # SQLAlchemy is noisy at INFO when echo is on; keep it opt-in.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DB_ECHO else logging.WARNING
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
