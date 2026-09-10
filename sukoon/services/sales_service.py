"""The sale transaction (Development Specification Phase 3, steps 3–4).

A sale, its line items, its stock deductions, and — for a credit sale — its Khata
ledger entry all commit in **one** transaction. A failure anywhere (not enough
stock, a bad line, a crash) rolls the whole thing back: no partial sale, no
half-deducted stock, no orphan ledger row, and no consumed invoice number
(Phase 3 Required Test — 'simulate a failure mid-sale and confirm no partial
state is left behind').

No Flask import (ADR-0003 §1). Discounts and tax are fixed at zero (ADR-0008 /
ADR-0020) — the sale flow has no path that sets them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, update

from sukoon.extensions import db
from sukoon.models import (
    CreditLedgerEntry,
    Customer,
    InvoiceCounter,
    Product,
    Sale,
    SaleItem,
)
from sukoon.services import inventory_service, invoicing, money, pricing
from sukoon.services.inventory_service import (
    FractionalQuantityError,
    validate_quantity_milli,
)

_INVOICE_PREFIX = "INV"
_PAYMENT_METHODS = {"cash", "card", "credit"}
_QUANTITY_SOURCES = {"stepper", "manual_weight", "manual_amount"}


# --- named errors (ADR-0003 §5) ---------------------------------------------


class SaleError(Exception):
    """Base for every failure in the sale flow."""


class EmptyCartError(SaleError):
    pass


class CartLineError(SaleError):
    def __init__(self, message: str, *, index: int | None = None):
        self.index = index
        super().__init__(message)


class PaymentError(SaleError):
    pass


# --- cart line -------------------------------------------------------------


@dataclass
class CartLine:
    """One row of the cart, already resolved to a product and a price.

    ``unit_price_paisa`` is the effective price (a price-override barcode may make
    it differ from ``product.sell_price_paisa`` — ADR-0009). ``typed_amount_paisa``
    is required exactly when ``quantity_source == 'manual_amount'`` and is what the
    line is charged (ADR-0007).
    """

    product: Product
    quantity_milli: int | None
    unit_price_paisa: int
    quantity_source: str
    typed_amount_paisa: int | None = None
    product_barcode_id: int | None = None


@dataclass
class CartSummary:
    """A cart priced for display, before payment. ``ready`` is false while any
    loose line is still waiting for a weight (glossary: 'Needs weight')."""

    line_totals_paisa: list[int | None]
    subtotal_paisa: int
    total_paisa: int
    ready: bool
    unweighed_count: int


def summarize_cart(lines: list[CartLine]) -> CartSummary:
    """Pure over ``CartLine`` — no I/O. Tolerates a line with no quantity yet
    (its total is ``None`` and the cart is not ready)."""
    totals: list[int | None] = []
    unweighed = 0
    for line in lines:
        no_quantity = line.quantity_milli is None or line.quantity_milli <= 0
        no_amount = (
            line.quantity_source == "manual_amount"
            and line.typed_amount_paisa is None
        )
        if no_quantity or no_amount:
            totals.append(None)
            unweighed += 1
            continue
        totals.append(
            pricing.line_total_paisa_for(
                quantity_source=line.quantity_source,
                quantity_milli=line.quantity_milli,
                unit_price_paisa=line.unit_price_paisa,
                typed_amount_paisa=line.typed_amount_paisa,
            )
        )
    subtotal = sum(t for t in totals if t is not None)
    return CartSummary(
        line_totals_paisa=totals,
        subtotal_paisa=subtotal,
        total_paisa=subtotal,  # no discount, no tax (ADR-0008 / ADR-0020)
        ready=bool(lines) and unweighed == 0,
        unweighed_count=unweighed,
    )


# --- invoice numbering (ADR-0016) -----------------------------------------


def _ensure_counter(now_year: int) -> None:
    if db.session.get(InvoiceCounter, 1) is None:
        db.session.add(
            InvoiceCounter(
                id=1, prefix=_INVOICE_PREFIX, year=now_year, next_sequence=1
            )
        )
        db.session.flush()


def claim_invoice_number(*, now: datetime | None = None) -> str:
    """Claim the next gap-free invoice number in one atomic step.

    A single ``UPDATE … RETURNING`` against the counter row: two terminals
    checking out in the same second serialise on that row's write lock, so
    neither a duplicate nor a gap is possible. The sequence resets to 1 on the
    first sale of a new calendar year (ADR-0016).

    Does **not** commit — the caller owns the transaction (``record_sale`` folds
    this into the sale's single commit; a standalone caller commits itself).
    """
    now = now or datetime.now(UTC)
    year = now.year
    _ensure_counter(year)

    stmt = (
        update(InvoiceCounter)
        .where(InvoiceCounter.id == 1)
        .values(
            year=year,
            next_sequence=case(
                (InvoiceCounter.year == year, InvoiceCounter.next_sequence + 1),
                else_=2,
            ),
        )
        .returning(InvoiceCounter.next_sequence)
    )
    new_next_sequence = db.session.execute(stmt).scalar_one()
    claimed = new_next_sequence - 1
    return invoicing.format_invoice_number(_INVOICE_PREFIX, year, claimed)


# --- the sale ------------------------------------------------------------


def _price_lines(lines: list[CartLine]) -> list[tuple[CartLine, int]]:
    priced: list[tuple[CartLine, int]] = []
    for i, line in enumerate(lines):
        if line.quantity_milli is None or line.quantity_milli <= 0:
            raise CartLineError(
                "A quantity greater than zero is required.", index=i
            )
        if line.quantity_source not in _QUANTITY_SOURCES:
            raise CartLineError(
                f"Unknown quantity source: {line.quantity_source}", index=i
            )
        try:
            validate_quantity_milli(
                line.quantity_milli,
                allows_fractional=line.product.allows_fractional,
            )
        except FractionalQuantityError as exc:
            raise CartLineError(str(exc), index=i) from exc

        if line.quantity_source == "manual_amount":
            if not line.product.allows_fractional:
                raise CartLineError(
                    "A sealed-pack item has no by-amount entry.", index=i
                )
            amount = line.typed_amount_paisa
            if amount is None or amount <= 0 or not money.is_whole_rupee(amount):
                raise CartLineError(
                    "A typed amount must be a whole number of rupees.", index=i
                )

        line_total = pricing.line_total_paisa_for(
            quantity_source=line.quantity_source,
            quantity_milli=line.quantity_milli,
            unit_price_paisa=line.unit_price_paisa,
            typed_amount_paisa=line.typed_amount_paisa,
        )
        priced.append((line, line_total))
    return priced


def record_sale(
    *,
    lines: list[CartLine],
    payment_method: str,
    user_id: int,
    customer_id: int | None = None,
    amount_tendered_paisa: int | None = None,
    terminal_label: str | None = None,
    now: datetime | None = None,
) -> Sale:
    """Ring up and persist one completed sale. All-or-nothing."""
    if not lines:
        raise EmptyCartError("Add at least one item before taking payment.")
    if payment_method not in _PAYMENT_METHODS:
        raise PaymentError(f"Unknown payment method: {payment_method}")

    customer: Customer | None = None
    if payment_method == "credit":
        if customer_id is None:
            raise PaymentError("A credit sale needs a customer (Khata).")
        customer = db.session.get(Customer, customer_id)
        if customer is None:
            raise PaymentError("That customer no longer exists.")

    priced = _price_lines(lines)
    subtotal = pricing.cart_subtotal_paisa([total for _, total in priced])
    total = subtotal  # no discount, no tax (ADR-0008 / ADR-0020)

    change_paisa: int | None = None
    if payment_method == "cash":
        if amount_tendered_paisa is None:
            amount_tendered_paisa = total
        if amount_tendered_paisa < total:
            raise PaymentError("Cash tendered is less than the total due.")
        change_paisa = amount_tendered_paisa - total
    else:
        amount_tendered_paisa = None

    try:
        invoice_number = claim_invoice_number(now=now)
        sale = Sale(
            invoice_number=invoice_number,
            customer_id=customer_id,
            user_id=user_id,
            terminal_label=terminal_label,
            subtotal_paisa=subtotal,
            discount_paisa=0,
            tax_paisa=0,
            total_paisa=total,
            payment_method=payment_method,
            amount_tendered_paisa=amount_tendered_paisa,
            change_paisa=change_paisa,
            status="completed",
        )
        db.session.add(sale)
        db.session.flush()  # assigns sale.id

        for line, line_total in priced:
            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=line.product.id,
                    product_barcode_id=line.product_barcode_id,
                    product_name_snapshot=line.product.name,
                    unit_price_paisa_snapshot=line.unit_price_paisa,
                    quantity_milli=line.quantity_milli,
                    quantity_source=line.quantity_source,
                    line_discount_paisa=0,
                    line_total_paisa=line_total,
                )
            )
            # commit=False: negative-stock guard still fires (raising here rolls
            # the whole sale back), but the write waits for the single commit.
            inventory_service.apply_stock_movement(
                product=line.product,
                movement_type="sale",
                quantity_milli=line.quantity_milli,
                reason=f"Sale {invoice_number}",
                user_id=user_id,
                reference_type="sale",
                reference_id=sale.id,
                commit=False,
            )

        if payment_method == "credit":
            new_balance = customer.balance_paisa + total
            db.session.add(
                CreditLedgerEntry(
                    customer_id=customer.id,
                    entry_type="credit_sale",
                    amount_paisa=total,
                    balance_after_paisa=new_balance,
                    sale_id=sale.id,
                    created_by_user_id=user_id,
                )
            )
            customer.balance_paisa = new_balance

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return sale
