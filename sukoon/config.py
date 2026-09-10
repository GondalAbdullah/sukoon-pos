"""Environment-driven configuration.

Per Operating Rule 6: no secret, API key, or credential is ever hardcoded here.
Every value that matters comes from the environment, typically populated locally
from a `.env` file that is never committed (see .env.example for the full list of
variables a deployment must supply).
"""
from __future__ import annotations

import os
import secrets
from datetime import timedelta


def _sqlite_uri(path: str) -> str:
    """Build an absolute-path SQLite URI. Relative paths are resolved against the
    project root so `flask db` and the app agree on one database file regardless
    of the working directory they are launched from."""
    if path == ":memory:":
        return "sqlite://"
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    return f"sqlite:///{abs_path}"


class Config:
    """Base configuration shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = os.environ.get("LOG_DIR", "logs")

    DATABASE_PATH = os.environ.get("DATABASE_PATH", "instance/sukoon.db")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or _sqlite_uri(
        os.environ.get("DATABASE_PATH", "instance/sukoon.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session-based auth (ADR-0008). A cashier's session should not outlive a
    # shift; the value is deliberately conservative and overridable per install.
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.environ.get("SESSION_LIFETIME_MINUTES", "600"))
    )
    SESSION_REFRESH_EACH_REQUEST = True

    # Brute-force lockout (ADR-0008). Numbers are config, not schema — tunable
    # without a migration. Defaults recorded in ADR-0017.
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    # An isolated in-memory database per app instance. A StaticPool keeps every
    # connection pointed at the same in-memory database for the life of the app.
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    # A real SECRET_KEY is still preferred even in tests; if none is supplied,
    # generate a throwaway one at runtime rather than hardcode a literal value
    # in source — this is a session-local dummy, not a real secret.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    LOGIN_LOCKOUT_MINUTES = 15
    LOGIN_MAX_ATTEMPTS = 5


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
