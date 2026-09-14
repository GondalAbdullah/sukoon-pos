"""Two workers, one queue (ADR-0033 §7–8): every message is sent exactly once and the
daily count never passes the cap. Real on-disk SQLite so the threads genuinely contend,
as in test_invoice_concurrency."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from sukoon.app import create_app
from sukoon.extensions import db
from sukoon.models import Customer, MessageDailyCount, NotificationQueue
from sukoon.services import settings_service
from sukoon.services.notifications import queue
from sukoon.services.notifications.providers.base import FakeProvider

NOW = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)


class ThreadSafeFake(FakeProvider):
    # a class-level lock: FakeProvider is a dataclass without __post_init__, so a
    # subclass's __post_init__ would never run (found the hard way — every send raised)
    _lock = threading.Lock()

    def send(self, message):
        with self._lock:
            return super().send(message)


@pytest.fixture
def file_app(tmp_path):
    app = create_app("development", config_overrides={
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'wa.db'}",
        "SECRET_KEY": "concurrency-test-only", "TESTING": True})
    with app.app_context():
        db.create_all()
        c = Customer(name="Busy Regular", phone_raw="0300 5541298",
                     phone_normalised="+923005541298",
                     phone_verified=True, whatsapp_opt_in=True, balance_paisa=0, is_active=True)
        db.session.add(c)
        db.session.flush()
        for i in range(20):
            db.session.add(NotificationQueue(
                customer_id=c.id, notification_type="credit_sale", dedupe_key=f"credit_sale:{i}",
                status="pending", attempt_count=0, created_at=NOW,
                payload_json=json.dumps({"items": "1 item", "amount": "Rs 600", "as_of": "x",
                                         "previous": "Settled", "new": "Rs 600 owed"})))
        settings_service.set(queue.REPLY_TO, "0300 1234567")
        settings_service.set(queue.ENABLED, "1")
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _drain(app, provider, workers=4, passes=6):
    def work(_):
        with app.app_context():
            for _ in range(passes):
                queue.process_due(provider, now=NOW, batch=25)
            db.session.remove()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, range(workers)))


def test_four_workers_send_every_message_exactly_once(file_app):
    provider = ThreadSafeFake()
    _drain(file_app, provider)
    with file_app.app_context():
        statuses = [r.status for r in db.session.scalars(db.select(NotificationQueue))]
        assert statuses.count("sent") == 20
        assert len(provider.sent) == 20 == len(provider.attempts)  # nobody sent a row twice
        assert db.session.get(MessageDailyCount, "2026-09-15").sent == 20


def test_racing_workers_never_pass_the_daily_cap(file_app):
    with file_app.app_context():
        settings_service.set(queue.DAILY_CAP, "12")
        db.session.commit()
    provider = ThreadSafeFake()
    _drain(file_app, provider)
    with file_app.app_context():
        assert len(provider.sent) == 12
        assert db.session.get(MessageDailyCount, "2026-09-15").sent == 12
        rows = list(db.session.scalars(db.select(NotificationQueue)))
        assert sum(r.status == "sent" for r in rows) == 12
        assert sum(r.status == "pending" for r in rows) == 8  # waiting, not lost or stuck
        assert queue.paused().kind == "cap"



def test_a_setting_saved_by_another_worker_mid_write_does_not_collide(file_app, monkeypatch):
    # The race behind a flaky full-suite failure, made deterministic: this worker looked
    # for "whatsapp.paused_kind", found nothing, and meanwhile another worker saved it.
    # Read-then-insert then inserted a duplicate key and crashed. (A thread-barrier version
    # of this test was tried first and passed even without the fix — it never lined up the
    # interleaving — so it was replaced rather than kept as false comfort.)
    with file_app.app_context():
        settings_service.set(queue.PAUSED_KIND, "cap")  # the other worker's committed write
        db.session.commit()
        db.session.remove()

        real_get = db.session.get

        def stale_get(model, key, *a, **k):
            from sukoon.models.system import Setting
            if model is Setting and key == queue.PAUSED_KIND:
                return None  # this worker's read happened before the other worker's commit
            return real_get(model, key, *a, **k)

        monkeypatch.setattr(db.session, "get", stale_get)
        settings_service.set(queue.PAUSED_KIND, "account")
        db.session.commit()  # the old read-then-insert raised IntegrityError here
        monkeypatch.undo()
        db.session.remove()
        assert settings_service.get(queue.PAUSED_KIND) == "account"
