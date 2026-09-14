"""Background jobs: the WhatsApp worker, monthly statements, the overdue check
(ADR-0001 APScheduler in-process; ADR-0031; ADR-0033 §7).

Started only by an explicit launcher (``python -m sukoon.run``), never by
``create_app`` — otherwise ``flask db upgrade`` or ``flask seed`` would grab the worker
lock and start sending. Only the process holding the lock runs jobs; a second copy of
Sukoon serves screens and sends nothing. The lock is an OS file lock, which the OS
releases when a process dies, so a crash can't leave a stale lock behind.
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask

from sukoon.extensions import db
from sukoon.services import clock
from sukoon.services.notifications import queue
from sukoon.services.notifications.providers.factory import build_provider

log = logging.getLogger(__name__)


class WorkerLock:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+")  # noqa: SIM115 — held open for the life of the process
        try:
            if sys.platform == "win32":  # pragma: no cover — Windows only (Phase 7)
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":  # pragma: no cover
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None


def provider_for(app: Flask):
    return build_provider(kind=app.config["WHATSAPP_PROVIDER"],
                          key_path=app.config["WHATSAPP_KEY_PATH"],
                          api_version=app.config.get("WHATSAPP_API_VERSION"))


def run_job(app: Flask, name: str):
    """One job run, in its own app context. Never raises into the scheduler."""
    with app.app_context():
        try:
            if name == "worker":
                return queue.process_due(provider_for(app))
            if name == "statements":
                return queue.run_statement_schedule()
            if name == "overdue":
                return queue.run_overdue_check()
            raise ValueError(f"Unknown job {name!r}")
        except Exception:  # noqa: BLE001
            log.exception("Background job %s failed; it will run again on schedule", name)
            db.session.rollback()
            return None
        finally:
            db.session.remove()


def start_scheduler(app: Flask) -> BackgroundScheduler | None:
    if not app.config.get("SCHEDULER_ENABLED", False):
        return None
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") not in (None, "true"):
        return None  # the reloader's watcher process
    lock = WorkerLock(app.config["WORKER_LOCK_PATH"])
    if not lock.acquire():
        log.info("Another copy of Sukoon runs the background jobs; this one won't send.")
        return None
    with app.app_context():
        zone = ZoneInfo(clock.shop_zone_name())
    scheduler = BackgroundScheduler(timezone=zone, job_defaults={
        "coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    scheduler.add_job(run_job, IntervalTrigger(minutes=1), args=[app, "worker"],
                      id="whatsapp-worker")
    scheduler.add_job(run_job, CronTrigger(day=1, hour=9, minute=0, timezone=zone),
                      args=[app, "statements"], id="whatsapp-statements")
    scheduler.add_job(run_job, CronTrigger(hour=11, minute=0, timezone=zone),
                      args=[app, "overdue"], id="whatsapp-overdue")
    # ADR-0031 §2: the start-up catch-up, once, as soon as the scheduler runs
    scheduler.add_job(run_job, args=[app, "statements"], id="whatsapp-statements-catch-up")
    scheduler.start()
    app.extensions["sukoon_scheduler"] = scheduler

    def _stop():
        if scheduler.running:
            scheduler.shutdown(wait=False)
        lock.release()

    atexit.register(_stop)
    log.info("Background jobs started (shop time %s)", zone.key)
    return scheduler
