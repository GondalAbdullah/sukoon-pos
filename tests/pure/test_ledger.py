"""Khata arithmetic (ADR-0014, ADR-0015, ADR-0026) — pure, hand-calculated."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from sukoon.services.ledger import (
    compute_over_limit,
    compute_overdue_status,
    compute_statement,
    describe_balance,
)

T0 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)


@dataclass
class E:
    created_at: datetime
    entry_type: str
    amount_paisa: int
    balance_after_paisa: int
    id: int = 0


def chain(*steps):
    """(day_offset, type, amount) -> entries with correct running balances."""
    out, bal = [], 0
    for i, (day, kind, amount) in enumerate(steps, start=1):
        bal += amount
        out.append(E(T0 + timedelta(days=day), kind, amount, bal, id=i))
    return out


# --- balance wording -----------------------------------------------------------

@pytest.mark.parametrize("balance,kind,amount", [
    (18_450_00, "owes", 18_450_00), (0, "settled", 0), (-200_00, "in_credit", 200_00),
])
def test_a_negative_balance_is_described_as_credit_never_negative(balance, kind, amount):
    state = describe_balance(balance)
    assert (state.kind, state.amount_paisa) == (kind, amount)


# --- credit limit (ADR-0014) --------------------------------------------------

def test_a_null_limit_is_never_enforced():
    assert compute_over_limit(10**9, 10**9, None) is None


def test_landing_exactly_on_the_limit_is_allowed_one_paisa_past_is_not():
    assert compute_over_limit(8_000_00, 2_000_00, 10_000_00) is None
    assert compute_over_limit(8_000_00, 2_000_01, 10_000_00) == 1


def test_the_check_is_after_the_sale_not_before():
    # under the limit before the sale, over it after
    assert compute_over_limit(9_000_00, 3_000_00, 10_000_00) == 2_000_00


def test_existing_credit_counts_toward_room():
    assert compute_over_limit(-500_00, 10_500_00, 10_000_00) is None


# --- overdue (ADR-0015) ------------------------------------------------------

NOW = T0 + timedelta(days=60)


def test_null_terms_are_never_overdue():
    assert not compute_overdue_status(chain((0, "credit_sale", 5_000_00)), None, NOW).is_overdue


def test_aged_from_the_first_credit_sale_when_no_payment_yet():
    s = compute_overdue_status(chain((0, "credit_sale", 1_000_00), (10, "credit_sale", 500_00)),
                               30, NOW)
    assert s.is_overdue and s.reference_date == T0 and s.days_overdue == 30  # 60 - 30


def test_a_payment_resets_the_clock_to_its_own_date():
    s = compute_overdue_status(
        chain((0, "credit_sale", 1_000_00), (45, "payment", -50_00)), 30, NOW)
    assert not s.is_overdue and s.reference_date == T0 + timedelta(days=45)


def test_refunds_and_adjustments_do_not_reset_the_clock():
    for kind in ("refund", "adjustment"):
        s = compute_overdue_status(
            chain((0, "credit_sale", 1_000_00), (50, kind, -100_00)), 30, NOW)
        assert s.is_overdue and s.reference_date == T0, kind


def test_a_fully_paid_customer_is_not_overdue_even_if_once_overdue():
    s = compute_overdue_status(chain((0, "credit_sale", 1_000_00), (55, "payment", -1_000_00)),
                               30, NOW + timedelta(days=100))
    assert not s.is_overdue


def test_exactly_at_the_terms_is_not_yet_overdue():
    s = compute_overdue_status(chain((0, "credit_sale", 1_000_00)), 60, NOW)
    assert not s.is_overdue


# --- statement --------------------------------------------------------------

def scenario():
    return chain(
        (0, "credit_sale", 18_000_00),   # Mar 1
        (4, "payment", -1_200_00),       # Mar 5
        (8, "credit_sale", 8_400_00),    # Mar 9
        (11, "payment", -10_000_00),     # Mar 12
        (31, "credit_sale", 3_250_00),   # Apr 1
        (33, "refund", -250_00),         # Apr 3
        (40, "payment", -20_700_00),     # Apr 10 — clears it, Rs 2,500 over
    )


def test_a_period_statement_matches_hand_calculated_values():
    april = compute_statement(scenario(), datetime(2026, 4, 1, tzinfo=UTC),
                              datetime(2026, 5, 1, tzinfo=UTC))
    # opening: 18,000 - 1,200 + 8,400 - 10,000 = 15,200
    assert april.opening_paisa == 15_200_00
    assert [r.running_paisa for r in april.rows] == [18_450_00, 18_200_00, -2_500_00]
    assert april.closing_paisa == -2_500_00           # in credit, explicitly
    assert (april.purchased_paisa, april.paid_paisa, april.refunded_paisa) == (
        3_250_00, 20_700_00, 250_00)
    assert april.opening_paisa + april.purchased_paisa - april.paid_paisa \
        - april.refunded_paisa == april.closing_paisa
    assert april.discrepancies == ()


def test_an_all_time_statement_starts_from_zero():
    s = compute_statement(scenario(), None, None)
    assert s.opening_paisa == 0 and len(s.rows) == 7 and s.closing_paisa == -2_500_00


def test_a_quiet_period_carries_the_balance_through():
    s = compute_statement(scenario(), datetime(2026, 3, 20, tzinfo=UTC),
                          datetime(2026, 3, 25, tzinfo=UTC))
    assert s.rows == () and s.opening_paisa == s.closing_paisa == 15_200_00


def test_a_stored_balance_that_disagrees_is_surfaced_not_trusted():
    entries = scenario()
    entries[2].balance_after_paisa += 1  # corrupt one cached balance
    s = compute_statement(entries, None, None)
    assert [r.entry.id for r in s.discrepancies] == [3]
