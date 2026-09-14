"""Khata — customers, the credit ledger, payments (Development Spec Phase 4;
ADR-0013, ADR-0014, ADR-0015, ADR-0026). No Flask.

``post_entry`` is the one writer of ``credit_ledger_entry``: it writes the row and
the ``customer.balance_paisa`` cache together, so the two can't drift. It does not
commit — callers fold it into their own transaction (a sale, a refund approval, a
payment). The arithmetic lives, pure, in ``services/ledger.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Customer, Payment, Sale, User
from sukoon.services import ledger, settings_service
from sukoon.services.auth_service import role_has_permission
from sukoon.services.phone import normalise_phone

DEFAULT_CREDIT_LIMIT_PAISA = 1_000_000  # Rs 10,000 — client's choice (ADR-0026 §2)
PAYMENT_METHODS = {
    "cash": "Cash",
    "bank_transfer": "Bank transfer",
    "mobile_wallet": "JazzCash / Easypaisa",
    "card": "Card",
}
VERIFY_METHODS = {"shown": "Shown on their phone", "called": "Rang the number"}


class KhataError(Exception):
    """Base for every Khata failure. Messages are written for the counter."""


class CustomerValidationError(KhataError):
    def __init__(self, message: str, *, field: str | None = None):
        self.field = field
        super().__init__(message)


class DuplicatePhoneError(KhataError):
    """Same normalised number already on another Khata (ADR-0013 §1) — confirmable."""

    def __init__(self, existing: list[Customer]):
        self.existing = existing
        names = ", ".join(c.name for c in existing)
        super().__init__(f"This number is already on {names}'s Khata. Same person?")


class OverpaymentError(KhataError):
    """More than they owe — confirmable, kept as credit (ADR-0026 §7)."""

    def __init__(self, excess_paisa: int):
        self.excess_paisa = excess_paisa
        super().__init__(
            f"That's Rs {excess_paisa // 100:,} more than they owe. Keep it as credit?"
        )


class CustomerHasBalanceError(KhataError):
    pass


class CreditLimitExceededError(KhataError):
    """ADR-0014: blocked unless an Admin authorises it."""

    def __init__(self, customer: Customer, over_by_paisa: int):
        self.customer = customer
        self.over_by_paisa = over_by_paisa
        super().__init__(
            f"This takes {customer.name} Rs {over_by_paisa // 100:,} over their "
            f"Rs {customer.credit_limit_paisa // 100:,} limit. An Admin can approve it."
        )


# --- the single ledger writer ----------------------------------------------------

def post_entry(
    customer: Customer,
    *,
    entry_type: str,
    amount_paisa: int,
    user_id: int,
    sale_id: int | None = None,
    payment_id: int | None = None,
    note: str | None = None,
    override_authorised_by_user_id: int | None = None,
) -> CreditLedgerEntry:
    new_balance = customer.balance_paisa + amount_paisa
    entry = CreditLedgerEntry(
        customer_id=customer.id,
        entry_type=entry_type,
        amount_paisa=amount_paisa,
        balance_after_paisa=new_balance,
        sale_id=sale_id,
        payment_id=payment_id,
        note=note,
        override_authorised_by_user_id=override_authorised_by_user_id,
        created_by_user_id=user_id,
    )
    db.session.add(entry)
    customer.balance_paisa = new_balance
    return entry


def entries_for(customer_id: int) -> list[CreditLedgerEntry]:
    return list(
        db.session.scalars(
            db.select(CreditLedgerEntry)
            .where(CreditLedgerEntry.customer_id == customer_id)
            .order_by(CreditLedgerEntry.created_at, CreditLedgerEntry.id)
        )
    )


def reconcile(customer: Customer) -> tuple[int, int]:
    """(cached balance, balance recomputed from the ledger). Equal, always."""
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(CreditLedgerEntry.amount_paisa), 0))
        .where(CreditLedgerEntry.customer_id == customer.id)
    )
    return customer.balance_paisa, int(total)


# --- customers ---------------------------------------------------------------------

def default_credit_limit_paisa() -> int:
    return settings_service.get_int("khata.default_credit_limit_paisa",
                                    DEFAULT_CREDIT_LIMIT_PAISA)


def _clean_phone(phone_raw: str | None) -> tuple[str | None, str | None]:
    raw = (phone_raw or "").strip() or None
    if raw is None:
        return None, None  # no phone is fine: a Khata doesn't need one (ADR-0013)
    normalised = normalise_phone(raw)
    if normalised is None:
        raise CustomerValidationError(
            "That doesn't look like a phone number — check the digits, e.g. 0300 1234567.",
            field="phone",
        )
    return raw, normalised


def find_duplicates(normalised: str | None, *, exclude_id: int | None = None) -> list[Customer]:
    if normalised is None:
        return []
    stmt = db.select(Customer).where(
        Customer.phone_normalised == normalised, Customer.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    return list(db.session.scalars(stmt))


def create_customer(
    *,
    name: str,
    phone_raw: str | None,
    user_id: int,
    address: str | None = None,
    notes: str | None = None,
    verified_method: str | None = None,
    whatsapp_opt_in: bool = False,
    confirm_duplicate: bool = False,
    now: datetime | None = None,
) -> Customer:
    clean_name = (name or "").strip()
    if not clean_name:
        raise CustomerValidationError("A name is required.", field="name")
    raw, normalised = _clean_phone(phone_raw)
    if not confirm_duplicate:
        dupes = find_duplicates(normalised)
        if dupes:
            raise DuplicatePhoneError(dupes)

    customer = Customer(
        name=clean_name,
        phone_raw=raw,
        phone_normalised=normalised,
        address=(address or "").strip() or None,
        notes=(notes or "").strip() or None,
        credit_limit_paisa=default_credit_limit_paisa(),
        balance_paisa=0,
    )
    db.session.add(customer)
    db.session.flush()
    if verified_method and normalised:
        _mark_verified(customer, verified_method, user_id, now)
    if whatsapp_opt_in and normalised:
        _mark_opted_in(customer, user_id, now)
    db.session.commit()
    _after_consent_saved(customer)
    return customer


def _mark_opted_in(customer: Customer, user_id: int, now: datetime | None) -> None:
    customer.whatsapp_opt_in = True
    customer.whatsapp_opt_in_at = now or datetime.now(UTC)
    customer.whatsapp_opt_in_by_user_id = user_id


def _clear_opt_in(customer: Customer) -> None:
    customer.whatsapp_opt_in = False
    customer.whatsapp_opt_in_at = None
    customer.whatsapp_opt_in_by_user_id = None


def _after_consent_saved(customer: Customer) -> None:
    """ADR-0028 §3 / ADR-0031: a ticked, unconfirmed number gets the account notice.
    After the commit, and never able to fail the save."""
    from sukoon.services.notifications import queue

    queue.safely(queue.on_customer_saved, customer)


def set_whatsapp_opt_in(customer: Customer, *, opted_in: bool, user_id: int,
                        now: datetime | None = None) -> None:
    """Tick or untick "Send updates on WhatsApp" (ADR-0028 §1). A customer with no
    number can't be ticked — there's nothing to send to."""
    if opted_in and customer.phone_normalised is None:
        raise CustomerValidationError("Add a phone number before ticking WhatsApp updates.",
                                      field="whatsapp_opt_in")
    if opted_in and not customer.whatsapp_opt_in:
        _mark_opted_in(customer, user_id, now)
    elif not opted_in and customer.whatsapp_opt_in:
        _clear_opt_in(customer)
    db.session.commit()
    if opted_in:
        _after_consent_saved(customer)


def _mark_verified(customer: Customer, method: str, user_id: int, now: datetime | None) -> None:
    if method not in VERIFY_METHODS:
        raise CustomerValidationError("Choose how the number was confirmed.", field="verify")
    customer.phone_verified = True
    customer.phone_verified_method = method
    customer.phone_verified_by_user_id = user_id
    customer.phone_verified_at = now or datetime.now(UTC)


def verify_phone(customer: Customer, *, method: str, user_id: int,
                 now: datetime | None = None) -> None:
    if customer.phone_normalised is None:
        raise CustomerValidationError("There's no number to confirm.", field="verify")
    _mark_verified(customer, method, user_id, now)
    db.session.commit()


def update_contact(
    customer: Customer,
    *,
    name: str,
    phone_raw: str | None,
    address: str | None,
    notes: str | None,
    confirm_duplicate: bool = False,
) -> Customer:
    clean_name = (name or "").strip()
    if not clean_name:
        raise CustomerValidationError("A name is required.", field="name")
    raw, normalised = _clean_phone(phone_raw)
    if normalised != customer.phone_normalised:
        if not confirm_duplicate:
            dupes = find_duplicates(normalised, exclude_id=customer.id)
            if dupes:
                raise DuplicatePhoneError(dupes)
        # a different number is an unconfirmed number (ADR-0026 §9), and agreement given
        # for the old number never carries to it (ADR-0028 §6)
        _clear_opt_in(customer)
        customer.phone_verified = False
        customer.phone_verified_method = None
        customer.phone_verified_by_user_id = None
        customer.phone_verified_at = None
    customer.name = clean_name
    customer.phone_raw = raw
    customer.phone_normalised = normalised
    customer.address = (address or "").strip() or None
    customer.notes = (notes or "").strip() or None
    db.session.commit()
    return customer


def set_credit_terms(customer: Customer, *, credit_limit_paisa: int | None,
                     credit_terms_days: int | None) -> Customer:
    if credit_limit_paisa is not None and credit_limit_paisa < 0:
        raise CustomerValidationError("A limit can't be negative.", field="credit_limit")
    if credit_limit_paisa is not None and credit_limit_paisa % 100:
        raise CustomerValidationError("Use whole rupees for the limit.", field="credit_limit")
    if credit_terms_days is not None and credit_terms_days <= 0:
        raise CustomerValidationError("Credit terms must be at least 1 day.",
                                      field="credit_terms")
    customer.credit_limit_paisa = credit_limit_paisa
    customer.credit_terms_days = credit_terms_days
    db.session.commit()
    return customer


def remove_customer(customer: Customer) -> str:
    """ADR-0026 §8: blocked unless the balance is exactly zero; a customer with any
    history is archived, never hard-deleted. Returns "archived" or "deleted"."""
    state = ledger.describe_balance(customer.balance_paisa)
    if state.kind == "owes":
        raise CustomerHasBalanceError(
            f"{customer.name} still owes Rs {state.amount_paisa // 100:,}. "
            "Settle the Khata before removing it."
        )
    if state.kind == "in_credit":
        raise CustomerHasBalanceError(
            f"{customer.name} is Rs {state.amount_paisa // 100:,} in credit. "
            "That has to be settled before the Khata can be removed."
        )
    has_history = any(
        db.session.scalar(db.select(db.func.count()).select_from(model)
                          .where(model.customer_id == customer.id))
        for model in (CreditLedgerEntry, Payment, Sale)
    )
    if has_history:
        customer.is_active = False
        db.session.commit()
        return "archived"
    db.session.delete(customer)
    db.session.commit()
    return "deleted"


# --- payments ---------------------------------------------------------------------

def record_payment(
    *,
    customer_id: int,
    amount_paisa: int | None,
    method: str,
    received_by_user_id: int,
    reference: str | None = None,
    allow_overpayment: bool = False,
) -> Payment:
    """Full, partial, or (confirmed) over-payment against the balance. One
    transaction: the payment row, its ledger entry, the cached balance."""
    customer = db.session.get(Customer, customer_id)
    if customer is None or not customer.is_active:
        raise KhataError("That Khata could not be found.")
    if method not in PAYMENT_METHODS:
        raise CustomerValidationError("Choose how they paid.", field="method")
    if amount_paisa is None or amount_paisa <= 0:
        raise CustomerValidationError("Enter the amount they paid.", field="amount")
    if amount_paisa % 100:
        raise CustomerValidationError("Use whole rupees.", field="amount")

    owed = max(customer.balance_paisa, 0)
    if amount_paisa > owed and not allow_overpayment:
        raise OverpaymentError(amount_paisa - owed)

    try:
        payment = Payment(
            customer_id=customer.id,
            amount_paisa=amount_paisa,
            method=method,
            reference=(reference or "").strip() or None,
            received_by_user_id=received_by_user_id,
        )
        db.session.add(payment)
        db.session.flush()
        post_entry(
            customer,
            entry_type="payment",
            amount_paisa=-amount_paisa,
            user_id=received_by_user_id,
            payment_id=payment.id,
            note=PAYMENT_METHODS[method] + (f" · {payment.reference}" if payment.reference else ""),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    from sukoon.services.notifications import queue  # after commit; can't fail the payment

    queue.safely(queue.on_payment, payment)
    return payment


# --- credit limit at the till (ADR-0014, ADR-0026 §6) ---------------------------

def check_credit_limit(customer: Customer, sale_total_paisa: int) -> None:
    over = ledger.compute_over_limit(customer.balance_paisa, sale_total_paisa,
                                     customer.credit_limit_paisa)
    if over is not None:
        raise CreditLimitExceededError(customer, over)


def require_override_authority(user_id: int | None) -> User:
    user = db.session.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active or not role_has_permission(
        user.role, "khata.override_limit"
    ):
        raise KhataError("Only an Admin can approve going over a credit limit.")
    return user


# --- reading ------------------------------------------------------------------------

@dataclass(frozen=True)
class CustomerRow:
    customer: Customer
    balance: ledger.BalanceState
    overdue: ledger.OverdueStatus
    near_limit: bool
    last_activity: datetime | None


LIST_FILTERS = ("all", "owing", "settled", "in_credit")


def list_customers(*, query: str | None = None, filter_: str = "all",
                   now: datetime | None = None) -> tuple[list[CustomerRow], dict[str, int]]:
    """Active customers with their balance state and overdue badge, newest activity
    first, plus a count per filter tab. One ledger query for the whole list."""
    now = now or datetime.now(UTC)
    stmt = db.select(Customer).where(Customer.is_active.is_(True))
    q = (query or "").strip()
    if q:
        like = f"%{q}%"
        digits = normalise_phone(q) or "".join(ch for ch in q if ch.isdigit())
        conds = [Customer.name.ilike(like), Customer.phone_raw.ilike(like)]
        if digits:
            conds.append(Customer.phone_normalised.like(f"%{digits.lstrip('+')[-7:]}%"))
        stmt = stmt.where(db.or_(*conds))
    customers = list(db.session.scalars(stmt))

    by_customer: dict[int, list[CreditLedgerEntry]] = {c.id: [] for c in customers}
    if customers:
        for e in db.session.scalars(
            db.select(CreditLedgerEntry).where(CreditLedgerEntry.customer_id.in_(by_customer))
        ):
            by_customer[e.customer_id].append(e)

    rows: list[CustomerRow] = []
    counts = dict.fromkeys(LIST_FILTERS, 0)
    for c in customers:
        entries = by_customer[c.id]
        state = ledger.describe_balance(c.balance_paisa)
        near = (
            c.credit_limit_paisa is not None and c.credit_limit_paisa > 0
            and c.balance_paisa * 5 >= c.credit_limit_paisa * 4  # 80%, integer maths
        )
        last = max((e.created_at for e in entries), default=None)
        row = CustomerRow(c, state, ledger.compute_overdue_status(entries, c.credit_terms_days,
                                                                  now), near, last)
        counts["all"] += 1
        counts[{"owes": "owing", "settled": "settled", "in_credit": "in_credit"}[state.kind]] += 1
        if filter_ == "all" or {"owes": "owing"}.get(state.kind, state.kind) == filter_:
            rows.append(row)

    rows.sort(key=lambda r: (r.last_activity is None,
                             -(r.last_activity.timestamp() if r.last_activity else 0),
                             r.customer.name.lower()))
    return rows, counts


def search_for_till(query: str, *, limit: int = 8) -> list[Customer]:
    rows, _ = list_customers(query=query)
    return [r.customer for r in rows[:limit]]
