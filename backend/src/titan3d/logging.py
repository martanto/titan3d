"""Loguru configuration; routes stdlib and uvicorn logging through loguru."""

import sys
import inspect
import logging
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    """Forward stdlib ``logging`` records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Re-emit a stdlib record through loguru, preserving the caller depth."""
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure loguru sinks and intercept stdlib/uvicorn loggers.

    Args:
        level: Minimum log level for all sinks.
        log_file: Optional rotating log file.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level=level,
            rotation="20 MB",
            retention=10,
            encoding="utf-8",
            enqueue=True,
        )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False
