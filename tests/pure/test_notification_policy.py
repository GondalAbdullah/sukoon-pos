"""WhatsApp rules — eligibility (ADR-0028), outcomes/retries/age (ADR-0029), reminder
cadence (ADR-0031). Pure."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sukoon.services.notifications.policy import (
    MAX_ATTEMPTS,
    Outcome,
    after_attempt,
    is_too_old,
    message_eligibility,
    reminder_block_reason,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def elig(t, **kw):
    base = dict(is_active=True, phone_normalised="+923005541298", opted_in=True,
                phone_verified=True)
    base.update(kw)
    return message_eligibility(notification_type=t, **base)


# --- eligibility --------------------------------------------------------------------

@pytest.mark.parametrize("t", ["credit_sale", "payment_receipt", "statement", "overdue_reminder",
                               "account_notice"])
def test_not_ticked_means_nothing_at_all(t):
    e = elig(t, opted_in=False)
    assert not e.allowed and e.reason == "Not ticked for WhatsApp updates"


@pytest.mark.parametrize("t", ["credit_sale", "payment_receipt", "statement", "overdue_reminder"])
def test_money_messages_need_a_confirmed_number(t):
    assert elig(t).allowed
    e = elig(t, phone_verified=False)
    assert not e.allowed and e.reason == "Number not confirmed"


def test_ticked_unconfirmed_gets_only_the_account_notice():
    assert elig("account_notice", phone_verified=False).allowed
    assert not elig("account_notice", phone_verified=True).allowed


@pytest.mark.parametrize("kw,reason", [({"is_active": False}, "Khata archived"),
                                       ({"phone_normalised": None}, "No phone number")])
def test_archived_or_numberless_customers_get_nothing(kw, reason):
    assert elig("credit_sale", **kw).reason == reason


def test_an_unknown_or_test_type_is_not_a_customer_message():
    assert not elig("birthday_wishes").allowed
    assert not elig("test").allowed


# --- outcomes ----------------------------------------------------------------------

def test_ok_is_sent_and_counts_toward_the_cap():
    n = after_attempt(Outcome.OK, 0, NOW)
    assert (n.status, n.attempt_count, n.counts_toward_cap) == ("sent", 1, True)


def test_no_connection_does_not_use_an_attempt():
    n = after_attempt(Outcome.NO_CONNECTION, 2, NOW)
    assert (n.status, n.attempt_count) == ("pending", 2)
    assert n.next_attempt_at == NOW + timedelta(minutes=1) and not n.counts_toward_cap


def test_retryable_backs_off_then_fails_after_five():
    delays, count = [], 0
    for _ in range(MAX_ATTEMPTS):
        n = after_attempt(Outcome.RETRYABLE, count, NOW)
        count = n.attempt_count
        if n.status == "pending":
            delays.append(n.next_attempt_at - NOW)
    assert delays == [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30),
                      timedelta(hours=2)]
    assert (n.status, n.attempt_count) == ("failed", 5)


def test_permanent_abandons_at_once():
    assert after_attempt(Outcome.PERMANENT, 0, NOW).status == "abandoned"


def test_account_broken_pauses_and_keeps_the_attempts():
    n = after_attempt(Outcome.ACCOUNT_BROKEN, 3, NOW)
    assert (n.status, n.attempt_count, n.pauses_queue) == ("pending", 3, True)


@pytest.mark.parametrize("t,limit", [("credit_sale", timedelta(hours=48)),
                                     ("payment_receipt", timedelta(hours=48)),
                                     ("statement", timedelta(days=7)),
                                     ("account_notice", timedelta(days=7)),
                                     ("overdue_reminder", timedelta(hours=24))])
def test_age_limits(t, limit):
    assert not is_too_old(t, NOW - limit, NOW)
    assert is_too_old(t, NOW - limit - timedelta(seconds=1), NOW)


def test_naive_timestamps_are_utc():
    assert is_too_old("overdue_reminder", datetime(2026, 9, 14, 11, 59), NOW)


# --- reminder cadence (ADR-0031) ------------------------------------------------------

def test_reminder_at_most_weekly_and_not_near_a_statement():
    assert reminder_block_reason(last_reminder_at=NOW - timedelta(days=6),
                                 last_statement_sent_at=None, now=NOW) == "Reminded 6 days ago"
    assert reminder_block_reason(last_reminder_at=NOW - timedelta(days=8),
                                 last_statement_sent_at=None, now=NOW) is None
    assert reminder_block_reason(last_reminder_at=None,
                                 last_statement_sent_at=NOW - timedelta(days=2),
                                 now=NOW) == "Statement sent 2 days ago"
    assert reminder_block_reason(last_reminder_at=None,
                                 last_statement_sent_at=NOW - timedelta(days=4), now=NOW) is None
