"""Run Sukoon with its background jobs: ``python -m sukoon.run``.

``flask run`` serves screens only — no WhatsApp worker, no statements, no reminders —
because the jobs must not start from ``create_app`` (see ``jobs/scheduler.py``). Phase 7
replaces the development server below with the packaged Windows service.
"""
from __future__ import annotations

import os

from sukoon.app import create_app
from sukoon.jobs.scheduler import start_scheduler


def main() -> None:
    app = create_app(os.environ.get("SUKOON_CONFIG"))
    start_scheduler(app)
    app.run(host=os.environ.get("SUKOON_HOST", "127.0.0.1"),
            port=int(os.environ.get("SUKOON_PORT", "5000")), use_reloader=False)


if __name__ == "__main__":
    main()
