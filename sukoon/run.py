"""Run Sukoon with its background jobs: ``python -m sukoon.run``.

``flask run`` serves screens only — no WhatsApp worker, no statements, no reminders, no
backups — because the jobs must not start from ``create_app`` (see ``jobs/scheduler.py``).

With ``SUKOON_CONFIG=production`` this is what ships (ADR-0035, ADR-0038): the data folder and
generated key, a backed-up migration, then **Waitress** on the shop's network. Flask's
development server is used only when the configuration is in debug mode.
"""
from __future__ import annotations

import logging
import os
import sys

from sukoon import startup
from sukoon.datadir import DataFolderError
from sukoon.jobs.scheduler import start_scheduler

log = logging.getLogger("sukoon.run")


def main() -> int:
    try:
        app = startup.build_app()
        if app.config.get("DATA_DIR"):
            startup.prepare_database(app)
    except (DataFolderError, startup.StartupError) as exc:
        # Before logging exists (a data folder problem) this is the only place it can go.
        if sys.stderr is not None:  # None in a windowed build
            print(f"Sukoon did not start: {exc}", file=sys.stderr)
        log.error("Sukoon did not start: %s", exc)
        return 2

    start_scheduler(app)
    port = int(os.environ.get("SUKOON_PORT", "5000"))
    if app.debug:
        app.run(host=os.environ.get("SUKOON_HOST", "127.0.0.1"), port=port, use_reloader=False)
        return 0

    from waitress import serve

    # The tills reach this PC over the shop's network (ADR-0038 §10); the installer's firewall
    # rule limits that to private networks.
    host = os.environ.get("SUKOON_HOST", "0.0.0.0")
    app.logger.info("Sukoon serving on %s:%s (data: %s)", host, port, app.config.get("DATA_DIR"))
    try:
        serve(app, host=host, port=port, threads=8, ident="Sukoon")
    except OSError as exc:
        # Most often another copy already holds the port. Under Task Scheduler nobody sees a
        # console, so the reason has to reach the log file.
        app.logger.error("Sukoon could not serve on %s:%s: %s", host, port, exc)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
