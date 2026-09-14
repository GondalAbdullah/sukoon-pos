"""Khata arithmetic — pure functions over already-fetched ledger rows (ADR-0014,
ADR-0015, ADR-0026). No database, no Flask.

A ledger row is anything with ``created_at``, ``entry_type``, ``amount_paisa``
(signed: a credit sale is +, a payment or refund is −) and ``balance_after_paisa``.
A positive balance is money the customer owes; a negative one is credit the shop
owes them (ADR-0026 §7) — never shown to a person as a bare negative.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


class _Entry(Protocol):
    created_at: datetime
    entry_type: str
    amount_paisa: int
    balance_after_paisa: int


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _ordered(entries: Iterable[_Entry]) -> list[_Entry]:
    return sorted(entries, key=lambda e: (_utc(e.created_at), getattr(e, "id", 0) or 0))


# --- balance, as a person reads it ----------------------------------------------

@dataclass(frozen=True)
class BalanceState:
    kind: str  # "owes" | "settled" | "in_credit"
    amount_paisa: int  # always >= 0


def describe_balance(balance_paisa: int) -> BalanceState:
    if balance_paisa > 0:
        return BalanceState("owes", balance_paisa)
    if balance_paisa < 0:
        return BalanceState("in_credit", -balance_paisa)
    return BalanceState("settled", 0)


# --- credit limit (ADR-0014) ------------------------------------------------------

def compute_over_limit(
    balance_paisa: int, sale_total_paisa: int, credit_limit_paisa: int | None
) -> int | None:
    """By how much a credit sale would take the balance past the limit, or None if
    it wouldn't. Compared *after* the sale: landing exactly on the limit is allowed.
    A NULL limit is never enforced."""
    if credit_limit_paisa is None:
        return None
    over = balance_paisa + sale_total_paisa - credit_limit_paisa
    return over if over > 0 else None


# --- overdue (ADR-0015) --------------------------------------------------------------

@dataclass(frozen=True)
class OverdueStatus:
    is_overdue: bool
    reference_date: datetime | None
    days_overdue: int  # days past the terms; 0 when not overdue


_NOT_OVERDUE = OverdueStatus(False, None, 0)


def compute_overdue_status(
    ledger_entries: Iterable[_Entry], credit_terms_days: int | None, now: datetime
) -> OverdueStatus:
    """Account-level staleness, exactly as ADR-0015 specifies. The clock starts at
    the most recent *payment*, else the first credit sale. A refund or an
    adjustment never resets it."""
    entries = _ordered(ledger_entries)
    if credit_terms_days is None or not entries:
        return _NOT_OVERDUE
    if entries[-1].balance_after_paisa <= 0:
        return _NOT_OVERDUE

    payments = [e for e in entries if e.entry_type == "payment"]
    sales = [e for e in entries if e.entry_type == "credit_sale"]
    if payments:
        reference = _utc(payments[-1].created_at)
    elif sales:
        reference = _utc(sales[0].created_at)
    else:
        return _NOT_OVERDUE

    days = (_utc(now) - reference).days
    if days > credit_terms_days:
        return OverdueStatus(True, reference, days - credit_terms_days)
    return OverdueStatus(False, reference, 0)


# --- statement (Development Spec Phase 4 step 4) --------------------------------------

@dataclass(frozen=True)
class StatementRow:
    entry: _Entry
    amount_paisa: int
    running_paisa: int


@dataclass(frozen=True)
class Statement:
    opening_paisa: int
    rows: Sequence[StatementRow]
    closing_paisa: int
    purchased_paisa: int  # credit sales in the period
    paid_paisa: int       # payments in the period (positive)
    refunded_paisa: int   # refunds in the period (positive)
    adjusted_paisa: int   # adjustments in the period (signed)
    # rows whose stored balance_after disagrees with the running total — should
    # always be empty; surfaced rather than silently trusted (ADR-0026 §10)
    discrepancies: Sequence[StatementRow] = field(default_factory=tuple)


def compute_statement(
    ledger_entries: Iterable[_Entry], start: datetime | None, end: datetime | None
) -> Statement:
    """The half-open period [start, end). ``None`` means from the first entry /
    up to now. The opening balance is the running total of everything before
    ``start``, recomputed from amounts rather than read from one stored row."""
    entries = _ordered(ledger_entries)
    lo = _utc(start) if start else None
    hi = _utc(end) if end else None

    opening = 0
    rows: list[StatementRow] = []
    discrepancies: list[StatementRow] = []
    running = 0
    purchased = paid = refunded = adjusted = 0
    for e in entries:
        when = _utc(e.created_at)
        running += e.amount_paisa
        if lo is not None and when < lo:
            opening = running
            continue
        if hi is not None and when >= hi:
            break
        row = StatementRow(e, e.amount_paisa, running)
        rows.append(row)
        if running != e.balance_after_paisa:
            discrepancies.append(row)
        if e.entry_type == "credit_sale":
            purchased += e.amount_paisa
        elif e.entry_type == "payment":
            paid += -e.amount_paisa
        elif e.entry_type == "refund":
            refunded += -e.amount_paisa
        else:
            adjusted += e.amount_paisa

    closing = rows[-1].running_paisa if rows else opening
    return Statement(opening, tuple(rows), closing, purchased, paid, refunded, adjusted,
                     tuple(discrepancies))
