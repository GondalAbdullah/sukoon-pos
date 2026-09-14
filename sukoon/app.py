"""Application factory.

Per ADR-0003: this module wires up config, logging, extensions, and blueprint
registration. It contains no business logic — anything that looks like a decision
belongs in services/, not here.
"""
from __future__ import annotations

import os

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
    # Wait for a lock rather than failing instantly: two terminals checking out
    # at once briefly contend on the invoice-counter row (Phase 3), and the
    # loser should queue, not raise "database is locked".
    cursor.execute("PRAGMA busy_timeout=5000")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:  # pragma: no cover - in-memory / unusual builds
        pass
    cursor.close()


def create_app(
    config_name: str | None = None,
    *,
    config_overrides: dict | None = None,
) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    if config_overrides:
        app.config.update(config_overrides)
    if not app.config.get("WHATSAPP_KEY_PATH"):
        app.config["WHATSAPP_KEY_PATH"] = os.path.join(app.instance_path, "whatsapp.key")
    if not app.config.get("WORKER_LOCK_PATH"):
        app.config["WORKER_LOCK_PATH"] = os.path.join(app.instance_path, "sukoon-worker.lock")

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
    from sukoon.routes.khata import bp as khata_bp
    from sukoon.routes.main import bp as main_bp
    from sukoon.routes.refunds import bp as refunds_bp
    from sukoon.routes.stock import bp as stock_bp
    from sukoon.routes.till import bp as till_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(till_bp)
    app.register_blueprint(refunds_bp)
    app.register_blueprint(khata_bp)

    _register_template_helpers(app)
    _register_cli(app)

    app.logger.info("Sukoon application created (config=%s)", config_name or "default")
    return app


def _register_template_helpers(app: Flask) -> None:
    """Display filters. Money is whole rupees (ADR-0007); quantity is milli-units
    (ADR-0004). Formatting only — no rounding decisions live here."""

    @app.context_processor
    def pending_refunds():
        """The approval queue had no way in — refunds sat pending unseen. Only
        someone who can approve gets the count (one COUNT per page render)."""
        from flask_login import current_user

        from sukoon.services import refund_service
        from sukoon.services.auth_service import role_has_permission

        ctx = {"pending_refund_count": 0, "khata_enabled": False}
        if current_user.is_authenticated:
            ctx["khata_enabled"] = role_has_permission(current_user.role, "khata.view")
            if role_has_permission(current_user.role, "sale.refund"):
                ctx["pending_refund_count"] = refund_service.count_pending()
        return ctx

    @app.template_test("match_initial")
    def match_initial(word: str) -> bool:
        return bool(word) and word[0].isalnum()

    @app.template_filter("balance_words")
    def balance_words(paisa: int) -> str:
        """A Khata balance as a person reads it — never a bare negative (ADR-0026 §7)."""
        from sukoon.services.statements import balance_words as words

        return words(paisa)

    @app.template_filter("shop_time")
    def shop_time(dt, fmt: str | None = None) -> str:
        """A stored UTC timestamp as the shop's wall-clock time (ADR-0024)."""
        from sukoon.services import clock

        return clock.format_shop_time(dt, fmt or clock.DISPLAY_FORMAT)

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
