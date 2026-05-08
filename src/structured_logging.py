"""Structured JSON logging for pipeline stages."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

# Pipeline stage constants
STAGE_FETCH = "fetch"
STAGE_FILTER = "filter"
STAGE_DEDUPLICATE = "deduplicate"
STAGE_RANK = "rank"
STAGE_SUMMARIZE = "summarize"
STAGE_PERSIST = "persist"
STAGE_PUBLISH = "publish"


class StructuredLogHandler(logging.Handler):
    """Emit logs as JSON with pipeline stage context."""

    def __init__(self, stage: str = "general"):
        super().__init__()
        self.stage = stage

    def emit(self, record: logging.LogRecord) -> None:
        """Convert log record to structured JSON format."""
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": self.stage,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }

            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.format(record)

            # Add any extra fields attached to the record
            for key in vars(record):
                if key not in (
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ):
                    log_entry[key] = getattr(record, key)

            print(json.dumps(log_entry, default=str))
        except Exception:
            self.handleError(record)


def configure_structured_logging(stage: str = "general", level: int = logging.INFO) -> None:
    """Configure logging to emit structured JSON output."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add structured handler
    structured_handler = StructuredLogHandler(stage=stage)
    root_logger.addHandler(structured_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with context support."""
    return logging.getLogger(name)


@contextmanager
def log_stage(
    stage: str,
    logger: logging.Logger | None = None,
    initial_context: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager for logging a pipeline stage with timing and metrics.

    Example:
        with log_stage("fetch", logger, {"source_count": 5}) as ctx:
            # ... do work ...
            ctx["articles_fetched"] = 42
            ctx["errors"] = 2
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    context: dict[str, Any] = initial_context or {}
    start_time = time.time()

    logger.info(
        f"Iniciando stage {stage}",
        extra={
            "stage_name": stage,
            "input_context": context,
        },
    )

    try:
        yield context
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error(
            f"Error en stage {stage}: {exc}",
            exc_info=True,
            extra={
                "stage_name": stage,
                "context": context,
                "elapsed_seconds": elapsed,
            },
        )
        raise
    else:
        elapsed = time.time() - start_time
        logger.info(
            f"Stage {stage} completado exitosamente",
            extra={
                "stage_name": stage,
                "context": context,
                "elapsed_seconds": elapsed,
            },
        )


@contextmanager
def log_operation(
    operation: str,
    logger: logging.Logger | None = None,
    details: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager for logging an operation with timing.

    Example:
        with log_operation("fetch_from_newsapi", logger, {"query": "AI"}) as op:
            op["articles"] = 15
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    details = details or {}
    start_time = time.time()

    logger.debug(
        f"Operacion iniciada: {operation}",
        extra={
            "operation": operation,
            "details": details,
        },
    )

    try:
        yield details
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.warning(
            f"Operacion {operation} fallida: {exc}",
            extra={
                "operation": operation,
                "details": details,
                "elapsed_seconds": elapsed,
            },
        )
        raise
    else:
        elapsed = time.time() - start_time
        logger.debug(
            f"Operacion {operation} completada",
            extra={
                "operation": operation,
                "details": details,
                "elapsed_seconds": elapsed,
            },
        )
