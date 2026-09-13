"""App-level error logging (docs/06-MONITORING.md, section A).

Every failed LLM call, swallowed background failure, and unhandled
exception is written to data/app.log next to the database. One stdlib
logger, one file, no dependencies — deliberately boring.

setup_logging() is idempotent and called once from main's lifespan;
get_logger() returns the app logger for the explicit call sites that
have something useful to say (the dashboard background thread, per-course
Roommate failures, provider retries that still fail).
"""
import logging
from pathlib import Path

from app.db import get_db_path

_LOGGER_NAME = "uib"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def setup_logging() -> logging.Logger:
    """Attach a FileHandler for data/app.log to the app logger.

    Idempotent per DATA_DIR: if a handler already points at the current
    data/app.log it is left alone (no duplicate lines); a stale handler
    pointing at a previous DATA_DIR (e.g. an earlier test's tmp dir) is
    closed and replaced so logs always land next to the current DB.
    """
    logger = get_logger()
    path = get_db_path().parent / "app.log"
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            if Path(h.baseFilename) == path:
                return logger
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger