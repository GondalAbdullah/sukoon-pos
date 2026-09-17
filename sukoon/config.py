"""Environment-driven configuration.

Per Operating Rule 6: no secret, API key, or credential is ever hardcoded here.
Every value that matters comes from the environment, typically populated locally
from a `.env` file that is never committed (see .env.example for the full list of
variables a deployment must supply).
"""
from __future__ import annotations

import os
import secrets
import tempfile
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _sqlite_uri(path: str) -> str:
    """Build an absolute-path SQLite URI. Relative paths are resolved against the
    project root so `flask db` and the app agree on one database file regardless
    of the working directory they are launched from.

    Pure: it creates nothing. It used to ``makedirs`` here, at import time and against
    the *current* directory — so an installed copy started by Windows from
    ``C:\\Windows\\System32`` would crash on import, before the launcher could point it at
    its data folder (ADR-0036). ``create_app`` creates the database's folder instead."""
    if path == ":memory:":
        return "sqlite://"
    abs_path = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
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
    # Said explicitly rather than left to the browser. A cookie with *no* SameSite attribute
    # gets Chromium's "Lax, except top-level POSTs within two minutes of being set" — and a
    # cashier who has just signed in holds exactly that cookie. Explicit Lax closes the window,
    # so another site's page can't submit a form into Sukoon on the cashier's session. This
    # matters from Phase 7, when Sukoon leaves localhost for the shop's network.
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True

    # The first password a person chooses in Sukoon is on the setup screen (ADR-0038 §6).
    # Length only, no composition rules — per NIST SP 800-63B, which found character-class
    # rules push people toward predictable passwords rather than strong ones.
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "8"))

    # Brute-force lockout (ADR-0008). Numbers are config, not schema — tunable
    # without a migration. Defaults recorded in ADR-0017.
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

    DEBUG = False
    TESTING = False

    # Phase 5 (ADR-0027, ADR-0033). The key and worker lock paths default into the
    # instance folder (set in create_app, which knows where that is).
    SCHEDULER_ENABLED = os.environ.get("SUKOON_SCHEDULER", "1") == "1"
    WHATSAPP_PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "meta")
    WHATSAPP_API_VERSION = os.environ.get("WHATSAPP_API_VERSION")
    WHATSAPP_KEY_PATH = os.environ.get("WHATSAPP_KEY_PATH")
    WORKER_LOCK_PATH = os.environ.get("SUKOON_WORKER_LOCK_PATH")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SCHEDULER_ENABLED = False
    WHATSAPP_PROVIDER = "fake"
    # never the real instance/ folder: a test saving a key must not write into the project
    WHATSAPP_KEY_PATH = os.path.join(tempfile.gettempdir(), f"sukoon-test-{os.getpid()}.key")
    WORKER_LOCK_PATH = os.path.join(tempfile.gettempdir(), f"sukoon-test-{os.getpid()}.lock")
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
