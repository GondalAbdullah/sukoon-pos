"""The WhatsApp outbox — queueing, sending, retrying, pausing (Development Spec Phase 5;
ADR-0028 … ADR-0033). No Flask.

Nothing here is ever called inside a sale or payment transaction: the hooks run after
the primary action has committed, through ``safely`` — a failure is logged and
swallowed, never raised into the till (ADR-0003 §6). The rules themselves are pure, in
``policy.py``; the wording is in ``templates.py``.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from sukoon.extensions import db
from sukoon.models import (
    CreditLedgerEntry,
    Customer,
    MessageDailyCount,
    NotificationQueue,
    Payment,
    Sale,
    StatementRun,
)
from sukoon.services import clock, ledger, settings_service
from sukoon.services.notifications import policy, templates
from sukoon.services.notifications.policy import Outcome
from sukoon.services.notifications.providers.base import OutgoingMessage, Provider, SendResult
from sukoon.services.phone import normalise_phone

log = logging.getLogger(__name__)

ENABLED = "whatsapp.enabled"
DAILY_CAP = "whatsapp.daily_cap"
REPLY_TO = "whatsapp.reply_to_number"
PAUSED_KIND = "whatsapp.paused_kind"      # "account" | "cap" | "config"
PAUSED_REASON = "whatsapp.paused_reason"
PAUSED_SINCE = "whatsapp.paused_since"
LAST_CHECK = "whatsapp.last_check_at"
DEFAULT_CAP = 200
STUCK_REASON = "Outcome unknown: Sukoon stopped while sending"


class NotReady(Exception):
    """Sending can't be switched on yet — the message says what's missing."""


# --- small helpers ----------------------------------------------------------------------

def _now(now: datetime | None) -> datetime:
    return policy.utc(now) if now else datetime.now(UTC)


def rs(paisa: int) -> str:
    return f"Rs {abs(paisa) // 100:,}"


def as_of_text(dt: datetime, *, with_time: bool = True) -> str:
    """'14 Sep 2026, 8:26 PM' — built by hand because %-I isn't portable to Windows."""
    local = clock.to_shop_time(dt)
    day = f"{local.day} {local.strftime('%b %Y')}"
    if not with_time:
        return day
    hour = local.hour % 12 or 12
    return f"{day}, {hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def safely(fn, *args, **kwargs):
    """Run a notification hook after a primary action committed. Never raises."""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 — by design: a message never breaks a sale
        log.exception("WhatsApp hook %s failed; the primary action is unaffected", fn.__name__)
        db.session.rollback()
        return None


def reply_to_number() -> str | None:
    return (settings_service.get(REPLY_TO) or "").strip() or None


def daily_cap() -> int:
    return max(settings_service.get_int(DAILY_CAP, DEFAULT_CAP), 0)


def is_enabled() -> bool:
    return settings_service.get(ENABLED) == "1"


# --- on / off (ADR-0033 §2–3) ------------------------------------------------------------

def set_enabled(on: bool, *, key_present: bool, now: datetime | None = None) -> int:
    """Switch sending on or off. Returns how many pending messages were abandoned."""
    now = _now(now)
    if on:
        missing = []
        if not key_present:
            missing.append("the WhatsApp access key")
        if not reply_to_number():
            missing.append("the shop's reply-to number")
        if missing:
            raise NotReady("Set " + " and ".join(missing) + " before switching sending on.")
        settings_service.set(ENABLED, "1")
        db.session.commit()
        return 0
    settings_service.set(ENABLED, "0")
    result = db.session.execute(
        update(NotificationQueue)
        .where(NotificationQueue.status == "pending")
        .values(status="abandoned", last_error="Sending switched off")
    )
    db.session.commit()
    return result.rowcount or 0


# --- pause state (ADR-0029 §7, ADR-0033 §4) -----------------------------------------------

@dataclass(frozen=True)
class Pause:
    kind: str
    reason: str
    since: str | None


def paused() -> Pause | None:
    kind = settings_service.get(PAUSED_KIND)
    if not kind:
        return None
    return Pause(kind, settings_service.get(PAUSED_REASON) or "",
                 settings_service.get(PAUSED_SINCE))


def _pause(kind: str, reason: str, now: datetime) -> None:
    settings_service.set(PAUSED_KIND, kind)
    settings_service.set(PAUSED_REASON, reason[:300])
    settings_service.set(PAUSED_SINCE, now.isoformat())
    # the failure that paused us counts as the latest check, so the next one is 30 minutes
    # away (ADR-0029 §9) rather than on the worker's very next minute
    settings_service.set(LAST_CHECK, now.isoformat())
    db.session.commit()
    log.warning("WhatsApp sending paused (%s): %s", kind, reason)


def _resume() -> None:
    for key in (PAUSED_KIND, PAUSED_REASON, PAUSED_SINCE):
        settings_service.set(key, None)
    db.session.commit()
    log.info("WhatsApp sending resumed")


def _shop_day(now: datetime) -> str:
    return clock.to_shop_time(now).strftime("%Y-%m-%d")


def sent_today(now: datetime | None = None) -> int:
    row = db.session.get(MessageDailyCount, _shop_day(_now(now)))
    return row.sent if row else 0


def _resume_if_possible(provider: Provider, now: datetime, *, force: bool = False) -> bool:
    p = paused()
    if p is None:
        return True
    if p.kind == "cap":
        if sent_today(now) < daily_cap():
            _resume()
            return True
        return False
    if p.kind == "config":
        if reply_to_number():
            _resume()
            return True
        return False
    last = settings_service.get(LAST_CHECK)
    due = force or last is None or now - policy.utc(datetime.fromisoformat(last)) \
        >= policy.RESUME_CHECK_EVERY
    if not due:
        return False
    settings_service.set(LAST_CHECK, now.isoformat())
    db.session.commit()
    try:
        result = provider.check()
    except Exception as exc:  # noqa: BLE001
        result = SendResult(Outcome.RETRYABLE, error=f"Check failed: {exc.__class__.__name__}")
    if result.outcome is Outcome.OK:
        _resume()
        return True
    if result.outcome is Outcome.ACCOUNT_BROKEN and result.error:
        settings_service.set(PAUSED_REASON, result.error[:300])
        db.session.commit()
    return False


def check_now(provider: Provider, now: datetime | None = None) -> bool:
    """An Admin's 'Check now' (ADR-0029 §9). True if sending is (now) not paused."""
    return _resume_if_possible(provider, _now(now), force=True)


# --- the daily cap, atomically (ADR-0033 §4, §8) -------------------------------------------

def _reserve(now: datetime) -> bool:
    day = _shop_day(now)
    db.session.execute(
        sqlite_insert(MessageDailyCount).values(day=day, sent=0).on_conflict_do_nothing()
    )
    result = db.session.execute(
        update(MessageDailyCount)
        .where(MessageDailyCount.day == day, MessageDailyCount.sent < daily_cap())
        .values(sent=MessageDailyCount.sent + 1)
    )
    db.session.commit()
    return result.rowcount == 1


def _release(now: datetime) -> None:
    db.session.execute(
        update(MessageDailyCount)
        .where(MessageDailyCount.day == _shop_day(now), MessageDailyCount.sent > 0)
        .values(sent=MessageDailyCount.sent - 1)
    )
    db.session.commit()


# --- queueing ----------------------------------------------------------------------------

def _eligibility(customer: Customer, notification_type: str) -> policy.Eligibility:
    return policy.message_eligibility(
        notification_type=notification_type,
        is_active=customer.is_active,
        phone_normalised=customer.phone_normalised,
        opted_in=customer.whatsapp_opt_in,
        phone_verified=customer.phone_verified,
    )


def enqueue(
    notification_type: str,
    *,
    customer: Customer,
    dedupe_key: str,
    payload: dict,
    now: datetime | None = None,
) -> NotificationQueue | None:
    """Queue one message, or nothing: switched off, not eligible, or already queued
    under this dedupe key. An unknown type is a programming error and raises."""
    if notification_type not in policy.CUSTOMER_TYPES:
        raise ValueError(f"Unknown WhatsApp message type: {notification_type!r}")
    if not is_enabled():
        return None
    if not _eligibility(customer, notification_type).allowed:
        return None
    if db.session.scalar(
        db.select(NotificationQueue.id).where(NotificationQueue.dedupe_key == dedupe_key)
    ) is not None:
        return None
    row = NotificationQueue(
        customer_id=customer.id,
        notification_type=notification_type,
        dedupe_key=dedupe_key,
        payload_json=json.dumps(payload),
        status="pending",
        attempt_count=0,
        created_at=_now(now),
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:  # a racing worker or a double click queued it first
        db.session.rollback()
        return None
    return row


# --- the events (ADR-0031, ADR-0032) ------------------------------------------------------

def on_credit_sale(sale: Sale, now: datetime | None = None) -> NotificationQueue | None:
    if sale.payment_method != "credit" or sale.customer_id is None:
        return None
    customer = db.session.get(Customer, sale.customer_id)
    entry = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.sale_id == sale.id,
                                           CreditLedgerEntry.entry_type == "credit_sale")
    )
    if customer is None or entry is None:
        return None
    new = entry.balance_after_paisa
    return enqueue("credit_sale", customer=customer, dedupe_key=f"credit_sale:{sale.id}", now=now,
                   payload={
                       "items": templates.items_phrase(len(sale.items)),  # lines, never names
                       "amount": rs(sale.total_paisa),
                       "as_of": as_of_text(sale.created_at),
                       "previous": ledger_words(new - entry.amount_paisa),
                       "new": ledger_words(new),
                   })


def on_payment(payment: Payment, now: datetime | None = None) -> NotificationQueue | None:
    customer = db.session.get(Customer, payment.customer_id)
    entry = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.payment_id == payment.id)
    )
    if customer is None or entry is None:
        return None
    return enqueue("payment_receipt", customer=customer, dedupe_key=f"payment:{payment.id}",
                   now=now, payload={
                       "amount": rs(payment.amount_paisa),
                       "as_of": as_of_text(payment.created_at),
                       "new": ledger_words(entry.balance_after_paisa),
                   })


def on_customer_saved(customer: Customer, now: datetime | None = None) -> NotificationQueue | None:
    """A ticked customer with an unconfirmed number gets the account notice, once per
    number (ADR-0028 §3, ADR-0031)."""
    if not customer.phone_normalised:
        return None
    return enqueue("account_notice", customer=customer, now=now,
                   dedupe_key=f"account_notice:{customer.id}:{customer.phone_normalised}",
                   payload={"name": customer.name})


def ledger_words(paisa: int) -> str:
    state = ledger.describe_balance(paisa)
    return {"owes": f"{rs(state.amount_paisa)} owed", "settled": "Settled",
            "in_credit": f"{rs(state.amount_paisa)} in credit"}[state.kind]


# --- monthly statements (ADR-0031 §1–2) -----------------------------------------------------

def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def statement_window(now: datetime) -> tuple[str, datetime, datetime]:
    """(target month 'YYYY-MM', window start, window end) for the month before ``now``'s
    shop-time month: 09:00 on the 1st until 09:00 on the 8th, shop time."""
    local = clock.to_shop_time(now)
    y, m = _previous_month(local.year, local.month)
    zone = local.tzinfo
    start = datetime(local.year, local.month, 1, 9, 0, tzinfo=zone).astimezone(UTC)
    end = datetime(local.year, local.month, 8, 9, 0, tzinfo=zone).astimezone(UTC)
    return f"{y:04d}-{m:02d}", start, end


def run_statement_schedule(now: datetime | None = None) -> str:
    """Called at 09:00 on the 1st and on every start-up. Returns what it did:
    'queued' | 'already' | 'not_yet' | 'skipped'."""
    from sukoon.services import statements  # statements -> khata_service; keep imports acyclic

    now = _now(now)
    key, start, end = statement_window(now)
    run = db.session.get(StatementRun, key)
    if run is not None and (run.queued_at or run.skipped_at):
        return "already"
    if now < start:
        return "not_yet"
    if run is None:
        run = StatementRun(month=key)
        db.session.add(run)
    if now >= end:
        run.skipped_at = now
        db.session.commit()
        log.warning("WhatsApp statements for %s skipped: Sukoon wasn't running 1st–8th", key)
        return "skipped"
    if is_enabled():
        period = statements.period_for(key)
        for customer in db.session.scalars(db.select(Customer).where(
                Customer.is_active.is_(True), Customer.whatsapp_opt_in.is_(True),
                Customer.phone_verified.is_(True))):
            doc = statements.build_statement(customer, period, now=now)
            if doc.closing_paisa == 0 and not doc.lines:
                continue  # settled and quiet: nothing to say
            enqueue("statement", customer=customer, dedupe_key=f"statement:{customer.id}:{key}",
                    now=now, payload={"month": period.label, "closing": doc.closing,
                                      "period": key})
    run.queued_at = now
    db.session.commit()
    return "queued"


# --- overdue reminders (ADR-0015, ADR-0031 §3–7) ---------------------------------------------

def _last_reminder_at(customer_id: int) -> datetime | None:
    return db.session.scalar(
        db.select(db.func.max(NotificationQueue.created_at)).where(
            NotificationQueue.customer_id == customer_id,
            NotificationQueue.notification_type == "overdue_reminder",
            NotificationQueue.status.in_(("pending", "sending", "sent")),
        )
    )


def _last_statement_sent_at(customer_id: int) -> datetime | None:
    return db.session.scalar(
        db.select(db.func.max(NotificationQueue.sent_at)).where(
            NotificationQueue.customer_id == customer_id,
            NotificationQueue.notification_type == "statement",
            NotificationQueue.status == "sent",
        )
    )


def reminder_block(customer: Customer, now: datetime | None = None) -> str | None:
    """Why an overdue reminder can't be sent to this customer now, in plain words, or
    None if it can. The Send reminder button shows this reason when disabled."""
    from sukoon.services import khata_service

    now = _now(now)
    if not is_enabled():
        return "WhatsApp sending is switched off"
    e = _eligibility(customer, "overdue_reminder")
    if not e.allowed:
        return e.reason
    status = ledger.compute_overdue_status(khata_service.entries_for(customer.id),
                                           customer.credit_terms_days, now)
    if not status.is_overdue:
        return "Not overdue"
    return policy.reminder_block_reason(last_reminder_at=_last_reminder_at(customer.id),
                                        last_statement_sent_at=_last_statement_sent_at(customer.id),
                                        now=now)


def queue_reminder(customer: Customer, now: datetime | None = None) -> NotificationQueue | None:
    now = _now(now)
    if reminder_block(customer, now) is not None:
        return None
    return enqueue("overdue_reminder", customer=customer, now=now,
                   dedupe_key=f"overdue:{customer.id}:{_shop_day(now)}",
                   payload={"balance": rs(customer.balance_paisa),
                            "as_of": as_of_text(now, with_time=False)})


def run_overdue_check(now: datetime | None = None) -> int:
    now = _now(now)
    if not is_enabled():
        return 0
    queued = 0
    for customer in db.session.scalars(db.select(Customer).where(
            Customer.is_active.is_(True), Customer.whatsapp_opt_in.is_(True),
            Customer.phone_verified.is_(True), Customer.credit_terms_days.is_not(None),
            Customer.balance_paisa > 0)):
        if queue_reminder(customer, now) is not None:
            queued += 1
    return queued


# --- sending --------------------------------------------------------------------------

def _outgoing(row: NotificationQueue, customer: Customer | None, to: str) -> OutgoingMessage:
    reply_to = reply_to_number()
    if reply_to is None:
        raise NotReady("No reply-to number is set, so no message can be worded.")
    payload = json.loads(row.payload_json or "{}")
    rendered = templates.render(row.notification_type, payload, reply_to=reply_to)
    document = None
    if row.notification_type == "statement" and customer is not None:
        from sukoon.services import statements

        doc = statements.build_statement(customer, statements.period_for(payload["period"]))
        document = statements.render_pdf(doc)
    return OutgoingMessage(to=to, template=rendered.template, language=templates.LANGUAGE,
                           params=rendered.params, text=rendered.text, document=document,
                           document_name=rendered.document_name)


def abandon_stuck(now: datetime | None = None) -> int:
    """ADR-0033 §9: 'sending' for 10 minutes means Sukoon stopped mid-send. Never resent."""
    now = _now(now)
    result = db.session.execute(
        update(NotificationQueue)
        .where(NotificationQueue.status == "sending",
               NotificationQueue.last_attempt_at < now - policy.STUCK_SENDING_AFTER)
        .values(status="abandoned", last_error=STUCK_REASON)
    )
    db.session.commit()
    return result.rowcount or 0


@dataclass
class RunSummary:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    abandoned: int = 0
    stopped: str | None = None  # why the run stopped early, if it did


def process_due(provider: Provider, *, now: datetime | None = None, batch: int = 25) -> RunSummary:
    """One pass of the worker: clean up stuck sends, respect off/paused, then send what's
    due. Safe to run from two processes at once (atomic claim and cap)."""
    now = _now(now)
    summary = RunSummary()
    abandon_stuck(now)
    if not is_enabled():
        summary.stopped = "off"
        return summary
    if not _resume_if_possible(provider, now):
        summary.stopped = "paused"
        return summary

    due_ids = list(db.session.scalars(
        db.select(NotificationQueue.id)
        .where(NotificationQueue.status == "pending",
               db.or_(NotificationQueue.next_attempt_at.is_(None),
                      NotificationQueue.next_attempt_at <= now))
        .order_by(NotificationQueue.created_at, NotificationQueue.id)
        .limit(batch)
    ))
    for row_id in due_ids:
        stop = _attempt(row_id, provider, now, summary)
        if stop:
            summary.stopped = stop
            break
    return summary


def _abandon(row: NotificationQueue, reason: str, summary: RunSummary) -> None:
    row.status = "abandoned"
    row.last_error = reason
    db.session.commit()
    summary.abandoned += 1


def _attempt(row_id: int, provider: Provider, now: datetime, summary: RunSummary) -> str | None:
    row = db.session.get(NotificationQueue, row_id)
    if row is None or row.status != "pending":
        return None
    if policy.is_too_old(row.notification_type, row.created_at, now):
        _abandon(row, "Too old to send", summary)
        return None
    customer = db.session.get(Customer, row.customer_id) if row.customer_id else None
    if customer is None:
        _abandon(row, "Customer no longer exists", summary)
        return None
    eligibility = _eligibility(customer, row.notification_type)  # ADR-0028 §5: re-check
    if not eligibility.allowed:
        _abandon(row, eligibility.reason or "No longer allowed", summary)
        return None
    try:
        message = _outgoing(row, customer, customer.phone_normalised)
    except NotReady as exc:
        _pause("config", str(exc), now)
        return "paused"

    # Claim first, then reserve a place under the cap. The other order let two workers
    # racing for one row both reserve, briefly inflating the count so a third message was
    # told "limit reached" early. A claimed row that can't get a place goes back untouched.
    claimed = db.session.execute(
        update(NotificationQueue)
        .where(NotificationQueue.id == row.id, NotificationQueue.status == "pending")
        .values(status="sending", last_attempt_at=now)
    ).rowcount
    db.session.commit()
    if claimed != 1:  # another worker got it first
        return None
    if not _reserve(now):
        db.session.execute(
            update(NotificationQueue)
            .where(NotificationQueue.id == row.id, NotificationQueue.status == "sending")
            .values(status="pending")
        )
        db.session.commit()
        _pause("cap", f"Daily message limit reached: {daily_cap()}. Sending resumes tomorrow, "
                      "or an Admin can raise the limit.", now)
        return "cap"

    try:
        result = provider.send(message)
    except Exception as exc:  # noqa: BLE001 — unknown failures retry, never count as sent
        result = SendResult(Outcome.RETRYABLE, error=f"Unexpected error: {exc.__class__.__name__}")

    db.session.refresh(row)
    nxt = policy.after_attempt(result.outcome, row.attempt_count, now)
    if not nxt.counts_toward_cap:
        _release(now)
    row.status = nxt.status
    row.attempt_count = nxt.attempt_count
    row.next_attempt_at = nxt.next_attempt_at
    if result.outcome is Outcome.OK:
        row.sent_at = now
        row.provider_message_id = result.message_id
        row.last_error = None
        summary.sent += 1
    else:
        row.last_error = (result.error or result.outcome.value)[:500]
        if nxt.status == "failed":
            summary.failed += 1
        elif nxt.status == "abandoned":
            summary.abandoned += 1
        else:
            summary.retried += 1
    db.session.commit()
    if nxt.pauses_queue:
        _pause("account", result.error or "The WhatsApp account can't send right now", now)
        return "paused"
    return None


# --- Admin actions (ADR-0033 §5, §10) -----------------------------------------------------------

def retry_now(row_id: int) -> bool:
    row = db.session.get(NotificationQueue, row_id)
    if row is None or row.status != "failed":
        return False
    row.status, row.attempt_count, row.next_attempt_at = "pending", 0, None
    db.session.commit()
    return True


def send_again(row_id: int, now: datetime | None = None) -> NotificationQueue | None:
    """A fresh copy of a failed or outcome-unknown message, queued now; its text still
    says 'as of' the original time, so it can't pretend to be current."""
    row = db.session.get(NotificationQueue, row_id)
    if row is None or row.status not in ("failed", "abandoned") or row.customer_id is None:
        return None
    copy = NotificationQueue(
        customer_id=row.customer_id, notification_type=row.notification_type,
        dedupe_key=f"{row.dedupe_key}#again-{uuid.uuid4().hex[:8]}",
        payload_json=row.payload_json, status="pending", attempt_count=0, created_at=_now(now),
    )
    db.session.add(copy)
    db.session.commit()
    return copy


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str


def send_test(provider: Provider, number_raw: str, now: datetime | None = None) -> TestResult:
    """ADR-0033 §10: bypasses the switch and consent (not a customer), counts toward the
    cap, is logged, and reports the real outcome in plain words."""
    now = _now(now)
    to = normalise_phone(number_raw)
    if to is None:
        return TestResult(False, "That doesn't look like a phone number.")
    reply_to = reply_to_number()
    if reply_to is None:
        return TestResult(False,
                          "Set the shop's reply-to number first — every message includes it.")
    if not _reserve(now):
        return TestResult(False, f"Today's message limit ({daily_cap()}) is already reached.")
    rendered = templates.render("test", {"name": "Al-Rehman General Store (test message)"},
                                reply_to=reply_to)
    row = NotificationQueue(customer_id=None, notification_type="test",
                            dedupe_key=f"test:{uuid.uuid4().hex}", status="sending",
                            attempt_count=0, last_attempt_at=now, created_at=now,
                            payload_json=json.dumps({"to": to}))
    db.session.add(row)
    db.session.commit()
    try:
        result = provider.send(OutgoingMessage(to=to, template=rendered.template,
                                               language=templates.LANGUAGE,
                                               params=rendered.params, text=rendered.text))
    except Exception as exc:  # noqa: BLE001
        result = SendResult(Outcome.RETRYABLE, error=f"Unexpected error: {exc.__class__.__name__}")
    row.attempt_count = 1
    if result.outcome is Outcome.OK:
        row.status, row.sent_at, row.provider_message_id = "sent", now, result.message_id
        db.session.commit()
        return TestResult(True, f"Sent to {number_raw.strip()}. Check that phone.")
    _release(now)
    row.status, row.last_error = "failed", (result.error or result.outcome.value)[:500]
    db.session.commit()
    words = {
        Outcome.NO_CONNECTION: "No internet connection from this PC.",
        Outcome.RETRYABLE: f"WhatsApp had a temporary problem ({result.error}). "
                           "Try again in a minute.",
        Outcome.PERMANENT: f"WhatsApp refused this message: {result.error}.",
        Outcome.ACCOUNT_BROKEN: f"The WhatsApp account can't send: {result.error}.",
    }
    if result.outcome is Outcome.ACCOUNT_BROKEN and is_enabled():
        _pause("account", result.error or "The WhatsApp account can't send right now", now)
    return TestResult(False, words[result.outcome])


# --- reading, for screens ----------------------------------------------------------------

def last_for_customer(customer_id: int) -> NotificationQueue | None:
    return db.session.scalar(
        db.select(NotificationQueue).where(NotificationQueue.customer_id == customer_id)
        .order_by(NotificationQueue.created_at.desc(), NotificationQueue.id.desc()).limit(1)
    )


def month_count(now: datetime | None = None) -> int:
    local = clock.to_shop_time(_now(now))
    start, end = clock.shop_month_bounds(local.year, local.month)
    return db.session.scalar(
        db.select(db.func.count(NotificationQueue.id)).where(
            NotificationQueue.status == "sent", NotificationQueue.sent_at >= start,
            NotificationQueue.sent_at < end)
    ) or 0


def log_rows(status: str | None = None, limit: int = 100) -> list[NotificationQueue]:
    stmt = db.select(NotificationQueue).order_by(NotificationQueue.created_at.desc(),
                                                 NotificationQueue.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(NotificationQueue.status == status)
    return list(db.session.scalars(stmt))


TYPE_LABELS = {
    "credit_sale": "Credit sale", "payment_receipt": "Payment receipt",
    "account_notice": "Account notice", "statement": "Statement",
    "overdue_reminder": "Overdue reminder", "test": "Test message",
}
