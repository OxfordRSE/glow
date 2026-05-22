import time
import logging
from contextlib import contextmanager
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)


@contextmanager
def log_duration(
    task: str,
    **extra: Any,
) -> Generator[dict[str, Any], None, None]:
    start = time.perf_counter()
    metrics = dict(extra)

    try:
        yield metrics

    finally:
        duration_s = time.perf_counter() - start

        logger.info(
            "%s completed",
            task,
            extra={
                "task": task,
                "duration_s": duration_s,
                **metrics,
            },
        )
