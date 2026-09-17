"""Starting an installed Sukoon (ADR-0035, ADR-0036, ADR-0038 §7, §11).

The launcher (``sukoon.run``) calls these in order:

1. ``build_app`` — point the app at the data folder and its generated session key. Only the
   *production* configuration uses the data folder; development and tests never touch it.
2. ``prepare_database`` — bring the database to the current schema **safely**: back it up
   first, and if the migration fails put the backup back and stop with a clear message, rather
   than leave a half-migrated database for the shop to sell against. Then fill in the
   permission table, so a new release's permissions exist before anyone signs in.

``create_app`` stays free of all of this, so tests and ``flask`` commands have no side effects.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import Flask
from sqlalchemy import inspect

from sukoon import backup, datadir
from sukoon.app import create_app
from sukoon.config import PROJECT_ROOT
from sukoon.extensions import db

log = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """Sukoon must not start. The message is written for whoever reads the log or the screen."""


def migrations_dir() -> Path:
    """Beside the package in development; inside the bundle once packaged by PyInstaller."""
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle) / "migrations" if bundle else PROJECT_ROOT / "migrations"


def build_app(config_name: str | None = None,
              environ: Mapping[str, str] = os.environ) -> Flask:
    config_name = config_name or environ.get("SUKOON_CONFIG")
    root = datadir.resolve(environ) if config_name == "production" else None
    if root is None:
        return create_app(config_name)
    layout = datadir.prepare(root)
    return create_app(config_name, config_overrides={
        "DATA_DIR": str(layout.root),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{layout.database}",
        "LOG_DIR": str(layout.logs),
        "BACKUP_DIR": str(layout.backups),
        "WHATSAPP_KEY_PATH": str(layout.whatsapp_key),
        "OFFSITE_SECRET_PATH": str(layout.offsite_secret),
        "BACKUP_KEY_PATH": str(layout.backup_encryption_key),
        "WORKER_LOCK_PATH": str(layout.worker_lock),
        "SECRET_KEY": environ.get("SECRET_KEY")
        or datadir.load_or_create_secret_key(layout.secret_key_file),
    })


def database_file(app: Flask) -> Path | None:
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    return Path(uri[len("sqlite:///"):]) if uri.startswith("sqlite:///") else None


def _head_revision(directory: Path) -> str:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(directory))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _current_revision() -> str | None:
    with db.engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _upgrade(directory: Path) -> None:
    from flask_migrate import upgrade

    upgrade(directory=str(directory))


def prepare_database(app: Flask, now: datetime | None = None) -> Path | None:
    """Migrate to the current schema, with a backup first. Returns that backup, if one was
    needed. Raises ``StartupError`` after restoring it if the migration fails."""
    from sukoon.seed import seed_permissions

    now = now or datetime.now(UTC)
    directory = migrations_dir()
    taken: Path | None = None
    with app.app_context():
        head = _head_revision(directory)
        current = _current_revision()
        db_path = database_file(app)

        if current is None:
            existing = set(inspect(db.engine).get_table_names()) - {"alembic_version"}
            if existing:
                raise StartupError(
                    f"The database at {db_path} has tables but no record of its schema version, "
                    f"so Sukoon can't tell how to upgrade it safely and has left it untouched. "
                    f"Tables found: {', '.join(sorted(existing))}.")

        if current != head:
            if current is not None and db_path is not None:
                backups_dir = Path(app.config.get("BACKUP_DIR") or db_path.parent / "backups")
                taken = backup.snapshot(
                    db_path, backups_dir / backup.pre_upgrade_name(now, current, head))
                log.info("Backed up before upgrading %s -> %s: %s", current, head, taken)
            db.engine.dispose()  # the migration opens its own connection
            try:
                _upgrade(directory)
            except Exception as exc:
                db.session.remove()
                db.engine.dispose()  # release the file before putting the backup back
                if taken is None:
                    raise StartupError(
                        f"Creating the database failed: {exc}. Nothing to restore — it was new."
                    ) from exc
                backup.restore(taken, db_path)
                raise StartupError(
                    f"Upgrading the database from {current} to {head} failed, so Sukoon put back "
                    f"the backup taken just before ({taken}) and has not started. The shop's data "
                    f"is as it was. The error was: {exc}") from exc
            log.info("Database upgraded %s -> %s", current or "(new)", head)

        seed_permissions()
    return taken
