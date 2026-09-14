"""The Messages screen, the Khata WhatsApp line, the consent tick on forms, and Send
reminder (ADR-0028, ADR-0031, ADR-0033)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sukoon.extensions import db
from sukoon.models import NotificationQueue
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import sales_service, settings_service
from sukoon.services.notifications import queue, secret_store
from sukoon.services.notifications.policy import Outcome
from sukoon.services.notifications.providers import factory
from sukoon.services.sales_service import CartLine
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

KEY = "EAAG-route-test-key"


@pytest.fixture
def setup(app, client, seeded, login, tmp_path):
    app.config["WHATSAPP_KEY_PATH"] = str(tmp_path / "whatsapp.key")
    seed_invoice_counter()
    factory._fake_singleton.sent.clear()
    factory._fake_singleton.outcomes.clear()
    factory._fake_singleton.check_outcomes.clear()
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=ghee, movement_type="stock_in", quantity_milli=100_000,
                             reason="in", user_id=seeded["admin"].id)
    return {"ghee": ghee, "key_path": tmp_path / "whatsapp.key", **seeded}


def _as(client, login, who):
    client.post("/logout")
    login(*({"cashier": ("T1", CASHIER_PASSWORD), "admin": ("Owner", ADMIN_PASSWORD)}[who]))


def _text(resp):
    return resp.get_data(as_text=True)


def _go_live(client, setup):
    client.post("/messages/key", data={"access_key": KEY})
    client.post("/messages/settings", data={"reply_to": "0300 1234567", "phone_number_id": "123",
                                            "daily_cap": "200"})
    return client.post("/messages/switch", data={"on": "1"}, follow_redirects=True)


# --- the Messages screen ------------------------------------------------------------

def test_only_an_admin_opens_messages(client, login, setup):
    _as(client, login, "cashier")
    assert client.get("/messages/").status_code == 403
    assert client.post("/messages/switch", data={"on": "1"}).status_code == 403
    assert "Messages" not in _text(client.get("/till/")).split("<main")[0]
    _as(client, login, "admin")
    html = _text(client.get("/messages/"))
    assert "Sending is off" in html and 'title="Messages' in html


def test_going_live_needs_key_and_reply_to_then_switches_on(client, login, setup):
    _as(client, login, "admin")
    resp = client.post("/messages/switch", data={"on": "1"}, follow_redirects=True)
    assert "Set the WhatsApp access key and the shop" in _text(resp)
    resp = _go_live(client, setup)
    assert "WhatsApp sending is on." in _text(resp) and queue.is_enabled()
    assert secret_store.load_key(setup["key_path"]) == KEY
    html = _text(client.get("/messages/"))
    assert KEY not in html and "Replace key" in html  # never shown again
    import sys
    assert ("Encrypted by Windows" in html) == (sys.platform == "win32")
    assert ("not encrypted" in html) == (sys.platform != "win32")  # never overstated


def test_settings_are_validated(client, login, setup):
    _as(client, login, "admin")
    resp = client.post("/messages/settings", data={"reply_to": "12", "daily_cap": "200"},
                       follow_redirects=True)
    assert "doesn&#39;t look like a phone number" in _text(resp)
    resp = client.post("/messages/settings", data={"reply_to": "0300 1234567", "daily_cap": "0"},
                       follow_redirects=True)
    assert "at least 1" in _text(resp)
    _go_live(client, setup)
    resp = client.post("/messages/settings", data={"reply_to": "", "daily_cap": "200"},
                       follow_redirects=True)
    assert "can&#39;t be removed" in _text(resp) and queue.reply_to_number() == "0300 1234567"


def test_send_test_while_off_reports_the_outcome(client, login, setup):
    _as(client, login, "admin")
    client.post("/messages/settings", data={"reply_to": "0300 1234567", "daily_cap": "200"})
    resp = client.post("/messages/test", data={"number": "0333 1112223"}, follow_redirects=True)
    assert "Sent to 0333 1112223. Check that phone." in _text(resp)
    assert factory._fake_singleton.sent[-1].to == "+923331112223"
    factory._fake_singleton.outcomes.append(Outcome.PERMANENT)
    resp = client.post("/messages/test", data={"number": "0333 1112223"}, follow_redirects=True)
    assert "WhatsApp refused this message" in _text(resp)


def test_switching_off_cancels_waiting_messages(client, login, setup):
    _as(client, login, "admin")
    _go_live(client, setup)
    c = khata.create_customer(name="R", phone_raw="0300 5541298", user_id=setup["cashier"].id,
                              whatsapp_opt_in=True)  # unconfirmed -> an account notice waits
    resp = client.post("/messages/switch", data={"on": "0"}, follow_redirects=True)
    assert "1 waiting message cancelled" in _text(resp)
    assert db.session.scalar(db.select(NotificationQueue)).status == "abandoned"
    assert c.id


def test_paused_banner_for_admins_everywhere_not_cashiers_and_check_now(client, login, setup):
    _as(client, login, "admin")
    _go_live(client, setup)
    queue._pause("account", "Error validating access token.", datetime.now(UTC))
    assert "WhatsApp messages are paused:" in _text(client.get("/stock/"))
    factory._fake_singleton.check_outcomes.append(Outcome.OK)
    resp = client.post("/messages/check", follow_redirects=True)
    assert "Sending is not paused" in _text(resp) and queue.paused() is None
    queue._pause("account", "Error validating access token.", datetime.now(UTC))
    _as(client, login, "cashier")
    assert "WhatsApp messages are paused" not in _text(client.get("/till/"))


def test_retry_and_send_again_from_the_log(client, login, setup):
    _as(client, login, "admin")
    _go_live(client, setup)
    c = khata.create_customer(name="R", phone_raw="0300 5541298", user_id=setup["cashier"].id,
                              whatsapp_opt_in=True)
    row = db.session.scalar(db.select(NotificationQueue))
    row.status, row.attempt_count = "failed", 5
    db.session.commit()
    html = _text(client.get("/messages/?status=failed"))
    assert "Retry now" in html and "Send again" in html
    client.post(f"/messages/{row.id}/retry")
    db.session.refresh(row)
    assert row.status == "pending"
    row.status, row.last_error = "abandoned", queue.STUCK_REASON
    db.session.commit()
    assert "outcome unknown" in _text(client.get("/messages/"))
    client.post(f"/messages/{row.id}/again")
    assert db.session.query(NotificationQueue).count() == 2 and c.id


# --- the Khata side --------------------------------------------------------------------

def test_opening_a_khata_with_the_tick(client, login, setup):
    _as(client, login, "cashier")
    assert "Send updates on WhatsApp" in _text(client.get("/khata/new"))
    assert 'name="whatsapp_opt_in" value="1" class="accent-teal mt-1" >' in _text(
        client.get("/khata/new"))  # never pre-ticked
    client.post("/khata/new", data={"name": "Ticked", "phone": "0300 5541298", "verify": "shown",
                                    "whatsapp_opt_in": "1"})
    c = db.session.scalar(db.select(khata.Customer))
    assert c.whatsapp_opt_in and c.whatsapp_opt_in_by_user_id == setup["cashier"].id


def test_a_changed_number_switches_updates_off_even_if_still_ticked(client, login, setup):
    c = khata.create_customer(name="R", phone_raw="0300 5541298", user_id=setup["cashier"].id,
                              verified_method="shown", whatsapp_opt_in=True)
    _as(client, login, "cashier")
    resp = client.post(f"/khata/{c.id}/edit", follow_redirects=True, data={
        "name": "R", "phone": "0321 9874512", "whatsapp_opt_in": "1"})
    assert "WhatsApp updates were switched off" in _text(resp)
    db.session.expire(c)
    assert not c.whatsapp_opt_in
    client.post(f"/khata/{c.id}/edit", data={"name": "R", "phone": "0321 9874512",
                                             "whatsapp_opt_in": "1"})
    db.session.expire(c)
    assert c.whatsapp_opt_in  # ticked again once the number stayed the same


def test_the_khata_shows_one_whatsapp_line_to_everyone(client, login, setup):
    c = khata.create_customer(name="R", phone_raw="0300 5541298", user_id=setup["cashier"].id,
                              verified_method="shown", whatsapp_opt_in=True)
    _as(client, login, "cashier")
    assert "WhatsApp sending is switched off for the shop" in _text(client.get(f"/khata/?c={c.id}"))
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    settings_service.set(queue.ENABLED, "1")
    db.session.commit()
    sales_service.record_sale(lines=[CartLine(product=setup["ghee"], quantity_milli=1000,
                                              unit_price_paisa=60_000, quantity_source="stepper")],
                              payment_method="credit", customer_id=c.id,
                              user_id=setup["cashier"].id)
    assert "Credit sale waiting to send" in _text(client.get(f"/khata/?c={c.id}"))
    queue.process_due(factory._fake_singleton)
    assert "Last WhatsApp update: credit sale, sent" in _text(client.get(f"/khata/?c={c.id}"))
    assert "Send reminder" not in _text(client.get(f"/khata/?c={c.id}"))  # Admin only


def test_send_reminder_is_admin_only_and_obeys_the_limits(client, login, setup):
    c = khata.create_customer(name="Late", phone_raw="0300 5541298", user_id=setup["cashier"].id,
                              verified_method="shown", whatsapp_opt_in=True)
    khata.set_credit_terms(c, credit_limit_paisa=None, credit_terms_days=30)
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    settings_service.set(queue.ENABLED, "1")
    db.session.commit()
    sales_service.record_sale(lines=[CartLine(product=setup["ghee"], quantity_milli=1000,
                                              unit_price_paisa=60_000, quantity_source="stepper")],
                              payment_method="credit", customer_id=c.id,
                              user_id=setup["cashier"].id)
    for e in khata.entries_for(c.id):
        e.created_at = datetime.now(UTC) - timedelta(days=45)
    db.session.commit()

    _as(client, login, "cashier")
    assert client.post(f"/khata/{c.id}/remind").status_code == 403
    _as(client, login, "admin")
    resp = client.post(f"/khata/{c.id}/remind", follow_redirects=True)
    assert "Reminder queued for Late." in _text(resp)
    resp = client.post(f"/khata/{c.id}/remind", follow_redirects=True)
    assert "No reminder sent: Reminded" in _text(resp)
    assert "Send reminder · Reminded" in _text(client.get(f"/khata/?c={c.id}"))
    assert len([r for r in db.session.scalars(db.select(NotificationQueue))
                if r.notification_type == "overdue_reminder"]) == 1
