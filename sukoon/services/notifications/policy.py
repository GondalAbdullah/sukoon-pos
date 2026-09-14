"""WhatsApp message rules — pure, no database, no Flask (ADR-0028, ADR-0029, ADR-0033).

Who may receive a message, how sending outcomes are classed, when to retry, and when to
give up. The queue applies these; nothing here touches a row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

MONEY_TYPES = frozenset({"credit_sale", "payment_receipt", "statement", "overdue_reminder"})
CUSTOMER_TYPES = MONEY_TYPES | {"account_notice"}
ALL_TYPES = CUSTOMER_TYPES | {"test"}


# --- eligibility (ADR-0028 §3) --------------------------------------------------------

@dataclass(frozen=True)
class Eligibility:
    allowed: bool
    reason: str | None = None  # plain words, shown to staff when not allowed


def message_eligibility(
    *,
    notification_type: str,
    is_active: bool,
    phone_normalised: str | None,
    opted_in: bool,
    phone_verified: bool,
) -> Eligibility:
    if notification_type not in CUSTOMER_TYPES:
        return Eligibility(False, f"Not a customer message type: {notification_type}")
    if not is_active:
        return Eligibility(False, "Khata archived")
    if not phone_normalised:
        return Eligibility(False, "No phone number")
    if not opted_in:
        return Eligibility(False, "Not ticked for WhatsApp updates")
    if notification_type == "account_notice":
        if phone_verified:
            return Eligibility(False, "Number already confirmed — no notice needed")
        return Eligibility(True)
    if not phone_verified:
        return Eligibility(False, "Number not confirmed")
    return Eligibility(True)


# --- outcomes, retries, age (ADR-0029) ---------------------------------------------

class Outcome(Enum):
    OK = "ok"
    NO_CONNECTION = "no_connection"   # doesn't use an attempt
    RETRYABLE = "retryable"           # uses an attempt, backs off
    PERMANENT = "permanent"           # this message can never go: abandon now
    ACCOUNT_BROKEN = "account_broken"  # nothing can go: pause the queue


MAX_ATTEMPTS = 5
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30),
           timedelta(hours=2), timedelta(hours=6))
NO_CONNECTION_RETRY = timedelta(minutes=1)
AGE_LIMITS = {
    "credit_sale": timedelta(hours=48),
    "payment_receipt": timedelta(hours=48),
    "account_notice": timedelta(days=7),
    "statement": timedelta(days=7),
    "overdue_reminder": timedelta(hours=24),
    "test": timedelta(hours=1),
}
STUCK_SENDING_AFTER = timedelta(minutes=10)   # ADR-0033 §9
RESUME_CHECK_EVERY = timedelta(minutes=30)    # ADR-0029 §9
REMINDER_EVERY = timedelta(days=7)            # ADR-0031 §3
NO_REMINDER_AFTER_STATEMENT = timedelta(days=3)


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def is_too_old(notification_type: str, queued_at: datetime, now: datetime) -> bool:
    limit = AGE_LIMITS.get(notification_type, timedelta(hours=24))
    return utc(now) - utc(queued_at) > limit


@dataclass(frozen=True)
class Next:
    status: str                    # "sent" | "pending" | "failed" | "abandoned"
    attempt_count: int
    next_attempt_at: datetime | None
    counts_toward_cap: bool        # only a message the API accepted is billed
    pauses_queue: bool = False


def after_attempt(outcome: Outcome, attempt_count: int, now: datetime) -> Next:
    """What a row becomes after one send attempt. ``attempt_count`` is before this one.
    An unknown outcome must be classed RETRYABLE by the adapter — never OK."""
    now = utc(now)
    if outcome is Outcome.OK:
        return Next("sent", attempt_count + 1, None, True)
    if outcome is Outcome.NO_CONNECTION:
        return Next("pending", attempt_count, now + NO_CONNECTION_RETRY, False)
    if outcome is Outcome.PERMANENT:
        return Next("abandoned", attempt_count + 1, None, False)
    if outcome is Outcome.ACCOUNT_BROKEN:
        return Next("pending", attempt_count, now + NO_CONNECTION_RETRY, False, pauses_queue=True)
    used = attempt_count + 1
    if used >= MAX_ATTEMPTS:
        return Next("failed", used, None, False)
    return Next("pending", used, now + BACKOFF[used - 1], False)


def reminder_block_reason(
    *, last_reminder_at: datetime | None, last_statement_sent_at: datetime | None,
    now: datetime,
) -> str | None:
    """ADR-0031 §3/§6: why an overdue reminder can't go yet, or None if it can."""
    now = utc(now)
    if last_reminder_at is not None and now - utc(last_reminder_at) < REMINDER_EVERY:
        return f"Reminded {_ago(now - utc(last_reminder_at))}"
    if last_statement_sent_at is not None and \
            now - utc(last_statement_sent_at) < NO_REMINDER_AFTER_STATEMENT:
        return f"Statement sent {_ago(now - utc(last_statement_sent_at))}"
    return None


def _ago(delta: timedelta) -> str:
    days = delta.days
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} ago"
    hours = delta.seconds // 3600
    return f"{hours} hour{'s' if hours != 1 else ''} ago" if hours else "just now"
