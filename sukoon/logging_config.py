"""Logging setup — a persistent, rotating diagnostic trail for a system that runs
unattended on a shop PC (Development Specification, Section 5)."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging(app) -> None:
    """Attach a rotating file handler plus a console handler to the Flask app's
    logger. Called once from the application factory."""
    log_dir = app.config.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "sukoon.log"),
        maxBytes=1_000_000,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(level)
    app.logger.propagate = False
