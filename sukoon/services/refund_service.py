"""Returns and refunds (Development Specification Phase 3 step 6; ADR-0020).

Two steps, and nothing moves between them:

* ``initiate_refund`` — a Cashier (``sale.refund_initiate``) records a
  ``pending_approval`` refund against an existing sale. No stock, no cash, no
  ledger entry.
* ``approve_refund`` — an Admin (``sale.refund`` + step-up) commits it: each
  line's stock goes back (unless flagged damaged), a credit sale's ledger is
  reversed, and the sale's status moves to ``partially_refunded`` / ``refunded``.
  All in one transaction.

No Flask import (ADR-0003 §1).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sukoon.extensions import db
from sukoon.models import (
    CreditLedgerEntry,
    Customer,
    Product,
    Refund,
    RefundItem,
    Sale,
    SaleItem,
)
from sukoon.services import inventory_service, pricing


class RefundError(Exception):
    """Base for every refund failure."""


class RefundLineError(RefundError):
    def __init__(self, message: str, *, sale_item_id: int | None = None):
        self.sale_item_id = sale_item_id
        super().__init__(message)


class RefundStateError(RefundError):
    """A refund was approved or rejected from the wrong state."""


@dataclass
class RefundLineSpec:
    sale_item_id: int
    quantity_milli: int
    restock: bool = True


_MILLI = 1000


# --- how much of a line is still refundable ------------------------------


def _refunded_milli_by_item(sale_id: int, *, statuses: tuple[str, ...]) -> dict[int, int]:
    rows = db.session.scalars(
        db.select(RefundItem)
        .join(Refund, RefundItem.refund_id == Refund.id)
        .where(Refund.sale_id == sale_id, Refund.status.in_(statuses))
    )
    out: dict[int, int] = defaultdict(int)
    for item in rows:
        out[item.sale_item_id] += item.quantity_milli
    return out


def refundable_quantity_milli(sale_item: SaleItem) -> int:
    """Sold quantity minus what is already covered by an approved *or*
    still-pending refund (so a line cannot be double-booked while an approval
    waits)."""
    claimed = _refunded_milli_by_item(
        sale_item.sale_id, statuses=("approved", "pending_approval")
    ).get(sale_item.id, 0)
    return max(0, sale_item.quantity_milli - claimed)


# --- step 1: initiate ---------------------------------------------------


def initiate_refund(
    *,
    sale_id: int,
    lines: list[RefundLineSpec],
    reason: str,
    initiated_by_user_id: int,
) -> Refund:
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        raise RefundError("That sale could not be found.")
    if not lines:
        raise RefundError("Select at least one line to refund.")
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise RefundError("A reason is required for a refund.")

    items_by_id = {item.id: item for item in sale.items}
    refund_items: list[RefundItem] = []
    total = 0

    for spec in lines:
        si = items_by_id.get(spec.sale_item_id)
        if si is None:
            raise RefundLineError(
                "That line is not part of this sale.", sale_item_id=spec.sale_item_id
            )
        if spec.quantity_milli is None or spec.quantity_milli <= 0:
            raise RefundLineError(
                "A refund quantity must be greater than zero.",
                sale_item_id=si.id,
            )

        available = refundable_quantity_milli(si)
        if si.quantity_source == "manual_amount":
            # ADR-0007: the typed money is authoritative and a partial weight is
            # meaningless — a by-amount line is refunded whole or not at all.
            if spec.quantity_milli != si.quantity_milli:
                raise RefundLineError(
                    "A by-amount line can only be refunded in full.",
                    sale_item_id=si.id,
                )
            if available < si.quantity_milli:
                raise RefundLineError(
                    "That line has already been refunded.", sale_item_id=si.id
                )
            line_total = si.line_total_paisa
        else:
            if spec.quantity_milli > available:
                raise RefundLineError(
                    f"Only {available / _MILLI:g} of that line is still refundable.",
                    sale_item_id=si.id,
                )
            line_total = pricing.compute_line_total_from_quantity(
                spec.quantity_milli, si.unit_price_paisa_snapshot
            )

        refund_items.append(
            RefundItem(
                sale_item_id=si.id,
                quantity_milli=spec.quantity_milli,
                line_total_paisa=line_total,
                restock=bool(spec.restock),
            )
        )
        total += line_total

    method = "credit_ledger" if sale.payment_method == "credit" else "cash"
    refund = Refund(
        sale_id=sale.id,
        total_paisa=total,
        method=method,
        reason=clean_reason,
        status="pending_approval",
        initiated_by_user_id=initiated_by_user_id,
    )
    refund.items = refund_items
    db.session.add(refund)
    db.session.commit()
    return refund


# --- step 2: approve / reject ----------------------------------------


def approve_refund(*, refund_id: int, approved_by_user_id: int) -> Refund:
    refund = db.session.get(Refund, refund_id)
    if refund is None:
        raise RefundError("That refund could not be found.")
    if refund.status != "pending_approval":
        raise RefundStateError(f"This refund is already {refund.status}.")

    sale = db.session.get(Sale, refund.sale_id)
    try:
        for item in refund.items:
            if not item.restock:
                continue
            sale_item = db.session.get(SaleItem, item.sale_item_id)
            product = db.session.get(Product, sale_item.product_id)
            inventory_service.apply_stock_movement(
                product=product,
                movement_type="refund",
                quantity_milli=item.quantity_milli,
                reason=f"Refund for {sale.invoice_number}",
                user_id=approved_by_user_id,
                reference_type="refund",
                reference_id=refund.id,
                commit=False,
            )

        if refund.method == "credit_ledger":
            customer = db.session.get(Customer, sale.customer_id)
            new_balance = customer.balance_paisa - refund.total_paisa
            db.session.add(
                CreditLedgerEntry(
                    customer_id=customer.id,
                    entry_type="refund",
                    amount_paisa=-refund.total_paisa,
                    balance_after_paisa=new_balance,
                    sale_id=sale.id,
                    created_by_user_id=approved_by_user_id,
                )
            )
            customer.balance_paisa = new_balance

        refund.status = "approved"
        refund.approved_by_user_id = approved_by_user_id
        refund.resolved_at = datetime.now(UTC)
        _recompute_sale_status(sale)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return refund


def reject_refund(*, refund_id: int, approved_by_user_id: int) -> Refund:
    refund = db.session.get(Refund, refund_id)
    if refund is None:
        raise RefundError("That refund could not be found.")
    if refund.status != "pending_approval":
        raise RefundStateError(f"This refund is already {refund.status}.")
    refund.status = "rejected"
    refund.approved_by_user_id = approved_by_user_id
    refund.resolved_at = datetime.now(UTC)
    db.session.commit()
    return refund


def _recompute_sale_status(sale: Sale) -> None:
    refunded = _refunded_milli_by_item(sale.id, statuses=("approved",))
    fully = all(
        refunded.get(item.id, 0) >= item.quantity_milli for item in sale.items
    )
    any_refunded = any(refunded.values())
    sale.status = (
        "refunded" if fully else "partially_refunded" if any_refunded else "completed"
    )


# --- reads -----------------------------------------------------------


def list_pending() -> list[Refund]:
    return list(
        db.session.scalars(
            db.select(Refund)
            .where(Refund.status == "pending_approval")
            .order_by(Refund.created_at)
        )
    )


def refunds_for_sale(sale_id: int) -> list[Refund]:
    return list(
        db.session.scalars(
            db.select(Refund)
            .where(Refund.sale_id == sale_id)
            .order_by(Refund.created_at)
        )
    )
