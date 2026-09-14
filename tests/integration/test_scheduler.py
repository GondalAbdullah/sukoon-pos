"""Background jobs and the one-worker lock (ADR-0031, ADR-0033 §7)."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from datetime import UTC, datetime

from sukoon.app import create_app
from sukoon.extensions import db
from sukoon.jobs.scheduler import WorkerLock, run_job, start_scheduler
from sukoon.models import Customer, NotificationQueue
from sukoon.services import settings_service
from sukoon.services.notifications import queue
from sukoon.services.notifications.providers import factory


def test_only_one_holder_of_the_worker_lock(tmp_path):
    first, second = WorkerLock(tmp_path / "w.lock"), WorkerLock(tmp_path / "w.lock")
    assert first.acquire()
    assert not second.acquire()  # a second copy of Sukoon
    first.release()
    assert second.acquire()
    second.release()


def test_a_crashed_holder_does_not_leave_a_stale_lock(tmp_path):
    lock_path = tmp_path / "w.lock"
    child = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(__import__('pathlib').Path.cwd())!r})
        from sukoon.jobs.scheduler import WorkerLock
        lock = WorkerLock({str(lock_path)!r})  # keep a reference, or GC closes the file
        assert lock.acquire()
        print("held", flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE, text=True)
    assert child.stdout.readline().strip() == "held"
    assert not WorkerLock(lock_path).acquire()
    child.kill()   # a crash, not a clean exit
    child.wait()
    lock = WorkerLock(lock_path)
    assert lock.acquire()  # the OS released it with the process
    lock.release()


def test_tests_and_cli_apps_never_start_jobs(app):
    assert app.config["SCHEDULER_ENABLED"] is False and start_scheduler(app) is None


def test_the_scheduler_starts_its_jobs_once_and_a_second_copy_does_not(tmp_path):
    overrides = {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 's.db'}",
                 "SECRET_KEY": "x", "SCHEDULER_ENABLED": True, "WHATSAPP_PROVIDER": "fake",
                 "WORKER_LOCK_PATH": str(tmp_path / "w.lock")}
    one = create_app("production", config_overrides=overrides)
    two = create_app("production", config_overrides=overrides)
    with one.app_context():
        db.create_all()
    sched = start_scheduler(one)
    try:
        assert sched is not None
        ids = {j.id for j in sched.get_jobs()} | {"whatsapp-statements-catch-up"}
        assert {"whatsapp-worker", "whatsapp-statements", "whatsapp-overdue"} <= ids
        stmt = sched.get_job("whatsapp-statements").trigger
        assert "day='1'" in str(stmt) and "hour='9'" in str(stmt)
        assert str(stmt.timezone) == "Asia/Karachi"
        assert start_scheduler(two) is None
    finally:
        sched.shutdown(wait=False)
        one.extensions.pop("sukoon_scheduler", None)


def test_the_worker_job_sends_through_the_configured_provider(app):
    factory._fake_singleton.sent.clear()
    c = Customer(name="R", phone_raw="0300 5541298", phone_normalised="+923005541298",
                 phone_verified=True, whatsapp_opt_in=True, balance_paisa=0, is_active=True)
    db.session.add(c)
    db.session.flush()
    db.session.add(NotificationQueue(
        customer_id=c.id, notification_type="account_notice", dedupe_key="n:1", status="pending",
        attempt_count=0, created_at=datetime.now(UTC), payload_json=json.dumps({"name": "R"})))
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    settings_service.set(queue.ENABLED, "1")
    db.session.commit()
    # the fake's rules: account_notice needs an unconfirmed number — so this row is abandoned
    # at the re-check, proving the job ran the real worker rather than a shortcut
    run_job(app, "worker")
    row = db.session.scalar(db.select(NotificationQueue))
    assert row.status == "abandoned"
    assert row.last_error == "Number already confirmed — no notice needed"


def test_a_failing_job_is_logged_not_raised(app, caplog):
    assert run_job(app, "no-such-job") is None
    assert "Background job no-such-job failed" in caplog.text
