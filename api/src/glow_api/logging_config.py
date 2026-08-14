"""Structured (JSON) logging configuration for the GLOW API.

Configures structlog so application code can emit structured events, and
attaches a shared stdlib handler/formatter so plain stdlib loggers (uvicorn's
access/error loggers, and any module using `logging.getLogger(__name__)`)
render through the same JSON pipeline. Every log line — structlog or
stdlib-originated — becomes one JSON object on stdout.
"""

import logging
import sys

import structlog

from glow_api.settings import settings


def configure_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.dict_tracebacks,
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    for name, level in (
        ("glow_api", settings.LOG_LEVEL),
        ("uvicorn.access", settings.LOG_UVICORN_ACCESS),
        ("uvicorn.error", settings.LOG_UVICORN),
    ):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
