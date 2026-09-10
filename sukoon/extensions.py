"""Shared extension singletons, instantiated here and initialised against the app
in the application factory. Kept as a single, uncontested place so every module
imports the same instance rather than creating its own (ADR-0003).
"""
from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

# A deterministic naming convention for every constraint and index. Without this,
# SQLite gets auto-generated names that Alembic cannot refer to when generating a
# downgrade, which breaks the up/down migration test this phase requires.
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=_naming_convention))
migrate = Migrate(render_as_batch=True)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
