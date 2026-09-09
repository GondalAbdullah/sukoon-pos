"""Application factory.

Per ADR-0003: this module wires up config, logging, and (from Phase 1 onward)
extensions and blueprints. It contains no business logic — anything that looks
like a decision belongs in services/, not here.
"""
from __future__ import annotations

from flask import Flask, render_template

from sukoon.config import get_config
from sukoon.logging_config import configure_logging


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    configure_logging(app)

    # Phase 1 onward: extensions.db.init_app(app), blueprint registration, etc.

    @app.route("/")
    def placeholder():
        return render_template("placeholder.html")

    app.logger.info("Sukoon application created (config=%s)", config_name or "default")
    return app


if __name__ == "__main__":
    create_app().run()
