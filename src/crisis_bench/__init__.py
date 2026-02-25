"""CrisisBench - LLM agent emergency detection benchmark."""

from __future__ import annotations

import logging
import os

import structlog

__version__ = "0.1.0"


def configure_logging(level: str | None = None) -> None:
    """Configure structlog for the project.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
            Defaults to LOG_LEVEL env var, or INFO.
    """
    log_level = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
