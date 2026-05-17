"""Structured logging setup."""
from __future__ import annotations

import logging
import sys


def setup_logging(
    level: str | int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """Configure root logger: level and optional format to stdout."""
    if format_string is None:
        format_string = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    logging.basicConfig(
        level=level,
        format=format_string,
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
