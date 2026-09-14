"""WhatsApp queue, consent, sending, retries, pausing, cap, scheduling (Development
Spec Phase 5; ADR-0028 … ADR-0033). Every test uses the fake provider."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from sukoon.extensions import db
from sukoon.models import NotificationQueue, Sale, StatementRun
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import sales_service, settings_service
from sukoon.services.notifications import queue
from sukoon.services.notifications.policy import Outcome
from sukoon.services.notifications.providers.base import FakeProvider
from sukoon.services.sales_service import CartLine

NOW = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)  # 12:00 in Pakistan


@pytest.fixture
def shop(seeded):
    seed_invoice_counter()
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    soap = inv.create_product(name="Private Item", sell_price_paisa=20_000)
    for p in (ghee, soap):
        inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=500_000,
                                 reason="in", user_id=seeded["admin"].id)
    return {"ghee": ghee, "soap": soap, **seeded}


def enable():
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    db.session.commit()
    queue.set_enabled(True, key_present=True)


def customer(shop, *, ticked=True, confirmed=True, phone="0300 5541298", name="Haji Usman"):
    c = khata.create_customer(name=name, phone_raw=phone, user_id=shop["cashier"].id,
                              verified_method="shown" if confirmed else None,
                              whatsapp_opt_in=ticked)
    khata.set_credit_terms(c, credit_limit_paisa=None, credit_terms_days=None)
    return c


def credit_sale(shop, c, *lines):
    return sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=n * 1000, unit_price_paisa=p.sell_price_paisa,
                        quantity_source="stepper") for p, n in lines],
        payment_method="credit", customer_id=c.id, user_id=shop["cashier"].id)


def rows(**where):
    stmt = db.select(NotificationQueue).order_by(NotificationQueue.id)
    for k, v in where.items():
        stmt = stmt.where(getattr(NotificationQueue, k) == v)
    return list(db.session.scalars(stmt))


# --- switched off / on (ADR-0033 §2–3) -----------------------------------------------------

def test_off_by_default_nothing_is_queued(shop):
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    assert rows() == []


def test_switching_on_needs_the_key_and_the_reply_to_number(shop):
    with pytest.raises(queue.NotReady, match="access key and the shop's reply-to number"):
        queue.set_enabled(True, key_present=False)
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    db.session.commit()
    with pytest.raises(queue.NotReady, match="access key"):
        queue.set_enabled(True, key_present=False)
    queue.set_enabled(True, key_present=True)
    assert queue.is_enabled()


def test_switching_off_abandons_pending_and_stops_queueing(shop):
    enable()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    assert queue.set_enabled(False, key_present=True) == 1
    assert rows()[0].status == "abandoned" and rows()[0].last_error == "Sending switched off"
    credit_sale(shop, c, (shop["ghee"], 1))
    assert len(rows()) == 1


# --- consent and eligibility (ADR-0028) ------------------------------------------------------

def test_a_new_customer_is_not_opted_in(shop):
    c = khata.create_customer(name="X", phone_raw="0300 5541298", user_id=shop["cashier"].id)
    assert c.whatsapp_opt_in is False


def test_not_ticked_means_nothing_for_any_message(shop):
    enable()
    c = customer(shop, ticked=False)
    credit_sale(shop, c, (shop["ghee"], 1))
    khata.record_payment(customer_id=c.id, amount_paisa=10_000, method="cash",
                         received_by_user_id=shop["cashier"].id)
    assert rows() == []


def test_ticked_unconfirmed_gets_one_account_notice_and_no_money_messages(shop):
    enable()
    c = customer(shop, confirmed=False)
    credit_sale(shop, c, (shop["ghee"], 1))
    [notice] = rows()
    assert notice.notification_type == "account_notice"
    khata.set_whatsapp_opt_in(c, opted_in=True, user_id=shop["cashier"].id)  # saved again
    assert len(rows()) == 1  # once per number
    khata.update_contact(c, name=c.name, phone_raw="0321 9874512", address=None, notes=None)
    khata.set_whatsapp_opt_in(c, opted_in=True, user_id=shop["cashier"].id)
    assert [r.dedupe_key for r in rows(notification_type="account_notice")] == [
        f"account_notice:{c.id}:+923005541298", f"account_notice:{c.id}:+923219874512"]


def test_a_confirmed_customer_needs_no_account_notice(shop):
    enable()
    customer(shop)
    assert rows() == []


def test_changing_the_number_clears_the_tick(shop):
    c = customer(shop)
    khata.update_contact(c, name=c.name, phone_raw="0321 9874512", address=None, notes=None)
    assert (c.whatsapp_opt_in, c.whatsapp_opt_in_at, c.whatsapp_opt_in_by_user_id) == (
        False, None, None)


def test_a_customer_without_a_number_cannot_be_ticked(shop):
    c = khata.create_customer(name="No Phone", phone_raw=None, user_id=shop["cashier"].id)
    with pytest.raises(khata.CustomerValidationError):
        khata.set_whatsapp_opt_in(c, opted_in=True, user_id=shop["cashier"].id)


def test_an_unknown_message_type_is_refused(shop):
    c = customer(shop)
    with pytest.raises(ValueError, match="Unknown WhatsApp message type"):
        queue.enqueue("birthday_wishes", customer=c, dedupe_key="x", payload={})


# --- events (ADR-0031, ADR-0032) -------------------------------------------------------------

def test_a_credit_sale_queues_one_notice_with_a_count_never_names(shop):
    enable()
    c = customer(shop)
    sale = credit_sale(shop, c, (shop["ghee"], 2), (shop["soap"], 1))
    [row] = rows(notification_type="credit_sale")
    payload = json.loads(row.payload_json)
    assert payload["items"] == "2 items" and payload["amount"] == "Rs 1,400"
    assert payload["previous"] == "Settled" and payload["new"] == "Rs 1,400 owed"
    assert "Private Item" not in row.payload_json and "Ghee" not in row.payload_json
    assert row.dedupe_key == f"credit_sale:{sale.id}"
    queue.on_credit_sale(sale)  # a second trigger for the same sale queues nothing
    assert len(rows(notification_type="credit_sale")) == 1


def test_a_sale_completes_even_when_queueing_blows_up(shop, monkeypatch):
    # the hard gate, part one: queueing runs after commit and can't raise into the sale
    enable()
    c = customer(shop)

    def boom(*a, **k):
        raise RuntimeError("queue on fire")
    monkeypatch.setattr(queue, "on_credit_sale", boom)
    sale = credit_sale(shop, c, (shop["ghee"], 1))
    assert db.session.get(Sale, sale.id) is not None and c.balance_paisa == 60_000


def test_a_sale_completes_with_the_provider_down_in_every_way(shop):
    # the hard gate, part two: nothing is sent inline, so provider failures can't touch it
    enable()
    c = customer(shop)
    for outcome in Outcome:
        provider = FakeProvider(outcomes=[outcome], raise_on_send=None)
        sale = credit_sale(shop, c, (shop["ghee"], 1))
        assert sale.id and provider.attempts == []  # the sale never called the provider
        queue.process_due(provider, now=datetime.now(UTC))
    assert db.session.query(Sale).count() == len(Outcome)


def test_a_payment_queues_a_receipt_and_overpayment_reads_as_credit(shop):
    enable()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    p = khata.record_payment(customer_id=c.id, amount_paisa=80_000, method="mobile_wallet",
                             reference="TX-1", received_by_user_id=shop["cashier"].id,
                             allow_overpayment=True)
    [row] = rows(notification_type="payment_receipt")
    payload = json.loads(row.payload_json)
    assert payload == {"amount": "Rs 800", "as_of": payload["as_of"], "new": "Rs 200 in credit"}
    assert "TX-1" not in row.payload_json and row.dedupe_key == f"payment:{p.id}"


# --- sending (ADR-0029) ---------------------------------------------------------------------

def _one_pending(shop, **kw):
    enable()
    c = customer(shop, **kw)
    credit_sale(shop, c, (shop["ghee"], 1))
    [row] = rows(notification_type="credit_sale")
    row.created_at = NOW
    db.session.commit()
    return c, row


def test_ok_sends_the_exact_wording_to_the_customer(shop):
    c, row = _one_pending(shop)
    provider = FakeProvider()
    assert queue.process_due(provider, now=NOW).sent == 1
    [msg] = provider.sent
    assert msg.to == "+923005541298" and msg.template == "sukoon_credit_sale"
    assert msg.text.startswith("Al-Rehman General Store: 1 item, Rs 600, added to your Khata")
    assert msg.text.endswith("For questions, contact the shop on 0300 1234567.")
    db.session.refresh(row)
    assert (row.status, row.attempt_count, row.provider_message_id) == ("sent", 1, "fake-1")
    assert queue.sent_today(NOW) == 1


def test_no_connection_uses_no_attempt_and_gives_up_at_the_age_limit(shop):
    c, row = _one_pending(shop)
    provider = FakeProvider(outcomes=[Outcome.NO_CONNECTION] * 3)
    queue.process_due(provider, now=NOW)
    db.session.refresh(row)
    assert (row.status, row.attempt_count) == ("pending", 0)
    assert row.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(minutes=1)
    assert queue.sent_today(NOW) == 0  # a failure isn't billed
    queue.process_due(provider, now=NOW + timedelta(hours=48, minutes=1))
    db.session.refresh(row)
    assert (row.status, row.last_error) == ("abandoned", "Too old to send")


def test_retryable_backs_off_then_fails_after_five_and_is_shown(shop):
    c, row = _one_pending(shop)
    provider = FakeProvider(outcomes=[Outcome.RETRYABLE] * 5)
    t = NOW
    for _ in range(5):
        queue.process_due(provider, now=t)
        db.session.refresh(row)
        if row.status == "pending":
            t = row.next_attempt_at.replace(tzinfo=UTC)
    assert (row.status, row.attempt_count, row.last_error) == ("failed", 5, "fake retryable")
    assert len(provider.attempts) == 5 and provider.sent == []


def test_permanent_abandons_on_the_first_attempt(shop):
    c, row = _one_pending(shop)
    queue.process_due(FakeProvider(outcomes=[Outcome.PERMANENT]), now=NOW)
    db.session.refresh(row)
    assert (row.status, row.attempt_count) == ("abandoned", 1)


def test_an_unexpected_exception_is_retried_never_marked_sent(shop):
    c, row = _one_pending(shop)
    queue.process_due(FakeProvider(raise_on_send=ConnectionResetError()), now=NOW)
    db.session.refresh(row)
    assert row.status == "pending" and row.attempt_count == 1
    assert row.last_error == "Unexpected error: ConnectionResetError"


def test_account_broken_pauses_the_queue_then_a_good_check_resumes_it(shop):
    c, row = _one_pending(shop)
    provider = FakeProvider(outcomes=[Outcome.ACCOUNT_BROKEN],
                            check_outcomes=[Outcome.ACCOUNT_BROKEN])
    assert queue.process_due(provider, now=NOW).stopped == "paused"
    db.session.refresh(row)
    assert (row.status, row.attempt_count) == ("pending", 0)
    assert queue.paused().kind == "account"
    # within 30 minutes: no check, still paused
    assert queue.process_due(provider, now=NOW + timedelta(minutes=10)).stopped == "paused"
    assert provider.checks == 0
    # at 30 minutes: the check fails -> still paused
    assert queue.process_due(provider, now=NOW + timedelta(minutes=31)).stopped == "paused"
    assert provider.checks == 1
    # 30 minutes later: the check passes -> resumes and sends
    summary = queue.process_due(provider, now=NOW + timedelta(minutes=62))
    assert queue.paused() is None and summary.sent == 1


def test_eligibility_is_rechecked_just_before_sending(shop):
    for i, change in enumerate(("untick", "archive", "unconfirm")):
        db.session.query(NotificationQueue).delete()
        db.session.commit()
        c, row = _one_pending(shop, name=f"C {change}", phone=f"0300 554129{i}")
        if change == "untick":
            khata.set_whatsapp_opt_in(c, opted_in=False, user_id=shop["cashier"].id)
        elif change == "archive":
            c.is_active = False
        else:
            c.phone_verified = False
        db.session.commit()
        provider = FakeProvider()
        queue.process_due(provider, now=NOW)
        db.session.refresh(row)
        assert row.status == "abandoned" and provider.attempts == [], change
        c.is_active, c.phone_verified = True, True
        db.session.commit()


def test_the_daily_cap_pauses_and_the_next_shop_day_resumes(shop):
    enable()
    settings_service.set(queue.DAILY_CAP, "2")
    db.session.commit()
    c = customer(shop)
    for _ in range(3):
        credit_sale(shop, c, (shop["ghee"], 1))
    for r in rows():
        r.created_at = NOW
    db.session.commit()
    provider = FakeProvider()
    summary = queue.process_due(provider, now=NOW)
    assert (summary.sent, summary.stopped) == (2, "cap")
    pause = queue.paused()
    assert pause.kind == "cap" and "Daily message limit reached: 2" in pause.reason
    assert [r.status for r in rows()] == ["sent", "sent", "pending"]  # the third waits, untouched
    tomorrow = NOW + timedelta(days=1)  # a new shop-time day
    assert queue.process_due(provider, now=tomorrow).sent == 1 and queue.paused() is None


def test_raising_the_cap_resumes_the_same_day(shop):
    enable()
    settings_service.set(queue.DAILY_CAP, "1")
    db.session.commit()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    credit_sale(shop, c, (shop["ghee"], 1))
    for r in rows():
        r.created_at = NOW
    db.session.commit()
    provider = FakeProvider()
    queue.process_due(provider, now=NOW)
    settings_service.set(queue.DAILY_CAP, "5")
    db.session.commit()
    assert queue.process_due(provider, now=NOW + timedelta(minutes=1)).sent == 1


def test_a_message_stuck_sending_is_never_resent(shop):
    c, row = _one_pending(shop)
    row.status, row.last_attempt_at = "sending", NOW - timedelta(minutes=11)
    db.session.commit()
    provider = FakeProvider()
    queue.process_due(provider, now=NOW)
    db.session.refresh(row)
    assert (row.status, row.last_error) == ("abandoned", queue.STUCK_REASON)
    assert provider.attempts == []
    copy = queue.send_again(row.id, now=NOW)  # an Admin's deliberate resend
    queue.process_due(provider, now=NOW)
    db.session.refresh(copy)
    assert copy.status == "sent" and copy.payload_json == row.payload_json


def test_a_message_just_claimed_is_left_alone(shop):
    c, row = _one_pending(shop)
    row.status, row.last_attempt_at = "sending", NOW - timedelta(minutes=5)
    db.session.commit()
    queue.process_due(FakeProvider(), now=NOW)
    db.session.refresh(row)
    assert row.status == "sending"


def test_retry_now_puts_a_failed_message_back(shop):
    c, row = _one_pending(shop)
    row.status, row.attempt_count = "failed", 5
    db.session.commit()
    assert queue.retry_now(row.id)
    queue.process_due(FakeProvider(), now=NOW)
    db.session.refresh(row)
    assert row.status == "sent"


# --- test send (ADR-0033 §10) ----------------------------------------------------------------

def test_send_test_works_while_off_counts_and_reports_plainly(shop):
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    db.session.commit()
    assert not queue.is_enabled()
    provider = FakeProvider()
    result = queue.send_test(provider, "0333 1112223", now=NOW)
    assert result.ok and result.message == "Sent to 0333 1112223. Check that phone."
    assert provider.sent[0].to == "+923331112223" and queue.sent_today(NOW) == 1
    [row] = rows(notification_type="test")
    assert row.customer_id is None and row.status == "sent"

    bad = queue.send_test(FakeProvider(outcomes=[Outcome.ACCOUNT_BROKEN]), "0333 1112223", now=NOW)
    assert not bad.ok and bad.message.startswith("The WhatsApp account can't send")
    assert queue.sent_today(NOW) == 1  # a failure isn't counted
    assert not queue.send_test(provider, "12", now=NOW).ok


def test_send_test_needs_the_reply_to_number(shop):
    assert "reply-to number" in queue.send_test(FakeProvider(), "0333 1112223", now=NOW).message


# --- statements (ADR-0031 §1–2) ---------------------------------------------------------------

def _pk(y, mo, d, h, mi=0):
    """A shop-time (UTC+5) instant as UTC."""
    return datetime(y, mo, d, h, mi, tzinfo=UTC) - timedelta(hours=5)


def test_statement_window_is_9am_on_the_1st_to_9am_on_the_8th_shop_time(shop):
    enable()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    for e in khata.entries_for(c.id):
        e.created_at = _pk(2026, 9, 20, 12)
    db.session.commit()
    assert queue.run_statement_schedule(now=_pk(2026, 10, 1, 8, 59)) == "not_yet"
    assert queue.run_statement_schedule(now=_pk(2026, 10, 1, 9, 0)) == "queued"
    assert queue.run_statement_schedule(now=_pk(2026, 10, 1, 9, 5)) == "already"
    [row] = rows(notification_type="statement")
    payload = json.loads(row.payload_json)
    assert payload == {"month": "September 2026", "closing": "Rs 600 owed", "period": "2026-09"}
    assert row.dedupe_key == f"statement:{c.id}:2026-09"


def test_catch_up_until_the_8th_then_the_month_is_skipped(shop):
    enable()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    # the PC was off on the 1st
    assert queue.run_statement_schedule(now=_pk(2026, 10, 5, 14)) == "queued"
    assert queue.run_statement_schedule(now=_pk(2026, 11, 9, 10)) == "skipped"  # off all week
    assert db.session.get(StatementRun, "2026-10").skipped_at is not None


def test_settled_and_quiet_customers_get_no_statement(shop):
    enable()
    customer(shop)
    queue.run_statement_schedule(now=_pk(2026, 10, 1, 9, 0))
    assert rows(notification_type="statement") == []


def test_a_statement_is_sent_with_its_pdf(shop):
    enable()
    c = customer(shop)
    credit_sale(shop, c, (shop["ghee"], 1))
    for e in khata.entries_for(c.id):
        e.created_at = _pk(2026, 9, 20, 12)
    db.session.commit()
    now = _pk(2026, 10, 1, 9, 0)
    queue.run_statement_schedule(now=now)
    provider = FakeProvider()
    queue.process_due(provider, now=now)
    msg = [m for m in provider.sent if m.template == "sukoon_statement"][0]
    assert msg.document.startswith(b"%PDF-")
    assert msg.document_name == "Khata statement September 2026.pdf"


# --- overdue reminders (ADR-0031 §3–7) --------------------------------------------------------

def _overdue(shop):
    enable()
    c = customer(shop)
    khata.set_credit_terms(c, credit_limit_paisa=None, credit_terms_days=30)
    credit_sale(shop, c, (shop["ghee"], 1))
    for r in rows():
        db.session.delete(r)
    for e in khata.entries_for(c.id):
        e.created_at = NOW - timedelta(days=45)
    db.session.commit()
    return c


def test_the_overdue_check_reminds_at_most_weekly(shop):
    c = _overdue(shop)
    assert queue.run_overdue_check(now=NOW) == 1
    [row] = rows(notification_type="overdue_reminder")
    assert json.loads(row.payload_json) == {"balance": "Rs 600", "as_of": "15 Sep 2026"}
    assert queue.run_overdue_check(now=NOW + timedelta(days=6)) == 0
    assert queue.reminder_block(c, now=NOW + timedelta(days=6)) == "Reminded 6 days ago"
    assert queue.run_overdue_check(now=NOW + timedelta(days=8)) == 1


def test_no_reminder_within_three_days_of_a_statement(shop):
    c = _overdue(shop)
    st = queue.enqueue("statement", customer=c, dedupe_key="statement:x", now=NOW,
                       payload={"month": "August 2026", "closing": "Rs 600 owed",
                                "period": "2026-08"})
    st.status, st.sent_at = "sent", NOW - timedelta(days=2)
    db.session.commit()
    assert queue.reminder_block(c, now=NOW) == "Statement sent 2 days ago"
    assert queue.run_overdue_check(now=NOW) == 0
    assert queue.reminder_block(c, now=NOW + timedelta(days=2)) is None


def test_a_manual_reminder_obeys_the_same_rules_and_cannot_double(shop):
    c = _overdue(shop)
    assert queue.queue_reminder(c, now=NOW) is not None
    assert queue.queue_reminder(c, now=NOW) is None  # a double press
    assert len(rows(notification_type="overdue_reminder")) == 1


def test_reminder_block_explains_why_not(shop):
    enable()
    c = customer(shop)
    assert queue.reminder_block(c, now=NOW) == "Not overdue"
    khata.set_whatsapp_opt_in(c, opted_in=False, user_id=shop["cashier"].id)
    assert queue.reminder_block(c, now=NOW) == "Not ticked for WhatsApp updates"
