"""Structured logging helpers for ETL jobs."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

try:
    from loguru import logger as _loguru_logger
except ModuleNotFoundError:  # pragma: no cover - depends on local env
    _loguru_logger = None


def configure_etl_logging() -> None:
    if _loguru_logger is not None:
        _loguru_logger.remove()
        _loguru_logger.add(sys.stdout, serialize=True)
        return
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")


def get_etl_logger(component: str):
    if _loguru_logger is not None:
        return _loguru_logger.bind(component=component, module="etl")
    return _StdJSONLogger(component=component)


class _StdJSONLogger:
    def __init__(self, *, component: str) -> None:
        self._component = component
        self._logger = logging.getLogger(f"etl.{component}")

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit("WARNING", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit("ERROR", message, **fields)

    def _emit(self, level: str, message: str, **fields: Any) -> None:
        payload = {"level": level, "component": self._component, "module": "etl", "event": message, **fields}
        line = json.dumps(payload, ensure_ascii=False)
        self._logger.info(line)
