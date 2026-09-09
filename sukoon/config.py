"""Environment-driven configuration.

Per Operating Rule 6: no secret, API key, or credential is ever hardcoded here.
Every value that matters comes from the environment, typically populated locally
from a `.env` file that is never committed (see .env.example for the full list of
variables a deployment must supply).
"""
from __future__ import annotations

import os
import secrets


class Config:
    """Base configuration shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = os.environ.get("LOG_DIR", "logs")

    # Wired up properly in Phase 1 when SQLAlchemy is introduced (ADR-0016).
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "instance/sukoon.db")

    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    # A real SECRET_KEY is still preferred even in tests; if none is supplied,
    # generate a throwaway one at runtime rather than hardcode a literal value
    # in source — this is a session-local dummy, not a real secret.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


class ProductionConfig(Config):
    DEBUG = False


config_by_name: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str | None = None) -> type[Config]:
    """Resolve a config class from an environment name, defaulting to development."""
    name = env_name or os.environ.get("FLASK_ENV", "development")
    return config_by_name.get(name, DevelopmentConfig)
