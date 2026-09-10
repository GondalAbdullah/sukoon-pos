"""Application factory.

Per ADR-0003: this module wires up config, logging, extensions, and blueprint
registration. It contains no business logic — anything that looks like a decision
belongs in services/, not here.
"""
from __future__ import annotations

import click
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from sukoon.config import get_config
from sukoon.extensions import db, login_manager, migrate
from sukoon.logging_config import configure_logging


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Every SQLite connection: enforce foreign keys (off by default in SQLite,
    which would silently void every FK constraint in ADR-0016) and use WAL mode
    for the concurrent-reader behaviour ADR-0001 depends on. Skipped for the
    in-memory test database, where WAL is meaningless and PRAGMA support varies.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:  # pragma: no cover - in-memory / unusual builds
        pass
    cursor.close()


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    configure_logging(app)

    if app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://":
        # Keep every connection pointed at the same in-memory database.
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Import models so their tables are registered on db.metadata for both
    # Alembic autogenerate and the test database's create_all().
    from sukoon import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, int(user_id))

    from sukoon.routes.admin import bp as admin_bp
    from sukoon.routes.auth import bp as auth_bp
    from sukoon.routes.main import bp as main_bp
    from sukoon.routes.stock import bp as stock_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(stock_bp)

    _register_template_helpers(app)
    _register_cli(app)

    app.logger.info("Sukoon application created (config=%s)", config_name or "default")
    return app


def _register_template_helpers(app: Flask) -> None:
    """Display filters. Money is whole rupees (ADR-0007); quantity is milli-units
    (ADR-0004). Formatting only — no rounding decisions live here."""

    @app.template_filter("rupees")
    def rupees(paisa: int | None) -> str:
        if paisa is None:
            return "—"
        return f"Rs {paisa // 100:,}"

    @app.template_filter("qty")
    def qty(milli: int | None, unit_label: str = "unit") -> str:
        if milli is None:
            return "—"
        whole = milli / 1000
        text = f"{int(whole)}" if milli % 1000 == 0 else f"{whole:g}"
        return f"{text} {unit_label}"


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    @click.option(
        "--sample/--no-sample",
        default=True,
        help="Also insert throwaway dev users and a sample catalogue.",
    )
    def seed(sample: bool) -> None:
        """Seed permissions (always) and optional local dev data."""
        from sukoon.seed import seed_all

        seed_all(with_sample_data=sample)
        click.echo("Seed complete (sample data: %s)." % ("yes" if sample else "no"))


if __name__ == "__main__":
    create_app().run()
