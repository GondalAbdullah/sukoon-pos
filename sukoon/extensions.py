"""Shared extension singletons, instantiated here and initialised against the app
in the application factory. Kept as a single, uncontested place so every module
imports the same instance rather than creating its own.

Populated in Phase 1 (SQLAlchemy, Alembic/Flask-Migrate, Flask-Login) — empty for
now because Phase 0 has no database or auth yet.
"""
from __future__ import annotations

# db = SQLAlchemy()           # Phase 1
# migrate = Migrate()         # Phase 1
# login_manager = LoginManager()  # Phase 1
