"""Structured logging with a per-request id."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time

from . import config

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": round(time.time(), 3), "level": record.levelname, "logger": record.name, "msg": record.getMessage(), "rid": request_id.get()}
        data.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


class _Plain(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()} [{request_id.get()}]"
        return base + ("\n" + self.formatException(record.exc_info) if record.exc_info else "")


def setup() -> None:
    root = logging.getLogger("vidya")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Json() if config.LOG_JSON else _Plain())
    root.addHandler(handler)
    root.setLevel(config.LOG_LEVEL if config.LOG_LEVEL in logging._nameToLevel else "INFO")
    root.propagate = False


def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(f"vidya.{name}")
