import logging
import sys
import os


def get_logger(name: str) -> logging.Logger:
    """
    Returns a named logger with consistent formatting.
    Reads LOG_LEVEL directly from environment to avoid
    circular import with config/settings.

    Usage in any file:
        from config.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Processing document")
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_level = os.getenv("LOG_LEVEL", "debug").upper()
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False

    return logger
