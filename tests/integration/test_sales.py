"""The sale transaction (Development Specification Phase 3 Required Tests;
edge-case matrix 'POS / Billing (Phase 3)' and 'Weighed-item entry (Phase 3)')."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sukoon.extensions import db
from sukoon.models import (
    CreditLedgerEntry,
    Customer,
    Sale,
    SaleItem,
    StockMovement,
    User,
)
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import sales_service
from sukoon.services.auth_service import hash_password
from sukoon.services.sales_service import CartLine

JAN_2026 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


@pytest.fixture
def user(app):
    u = User(name="Till", initials="TL", role="cashier", password_hash=hash_password("x"))
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def counter(app):
    seed_invoice_counter()


@pytest.fixture
def milk(app, user):
    p = inv.create_product(name="Olpers Milk 1L", sell_price_paisa=28_000)
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=20_000,
        reason="in", user_id=user.id,
    )
    return p


@pytest.fixture
def chana(app, user):
    p = inv.create_product(
        name="Kabuli Chana loose", sell_price_paisa=48_000,
        allows_fractional=True, unit_label="kg",
    )
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=10_000,
        reason="in", user_id=user.id,
    )
    return p


# --- the full journey -----------------------------------------------------

def test_a_full_cash_sale_persists_one_consistent_transaction(counter, user, milk, chana):
    sale = sales_service.record_sale(
        lines=[
            CartLine(product=milk, quantity_milli=4_000, unit_price_paisa=28_000,
                     quantity_source="stepper"),
            CartLine(product=chana, quantity_milli=750, unit_price_paisa=48_000,
                     quantity_source="manual_weight"),
        ],
        payment_method="cash",
        user_id=user.id,
        amount_tendered_paisa=200_000,
        now=JAN_2026,
    )

    assert sale.invoice_number == "INV-2026-0001"
    assert sale.subtotal_paisa == 112_000 + 36_000
    assert sale.total_paisa == 148_000
    assert sale.discount_paisa == 0 and sale.tax_paisa == 0
    assert sale.change_paisa == 200_000 - 148_000
    assert sale.status == "completed"

    items = db.session.query(SaleItem).filter_by(sale_id=sale.id).all()
    assert {i.product_name_snapshot for i in items} == {"Olpers Milk 1L", "Kabuli Chana loose"}
    assert milk.stock_quantity_milli == 16_000  # 20000 - 4000
    assert chana.stock_quantity_milli == 9_250  # 10000 - 750

    movements = db.session.query(StockMovement).filter_by(movement_type="sale").all()
    assert len(movements) == 2
    assert all(m.reference_type == "sale" and m.reference_id == sale.id for m in movements)


def test_invoice_numbers_increment_with_no_gaps(counter, user, milk):
    n1 = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    ).invoice_number
    n2 = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    ).invoice_number
    assert (n1, n2) == ("INV-2026-0001", "INV-2026-0002")


def test_the_invoice_year_turns_over_at_the_shops_midnight(counter, user, milk):
    # ADR-0024: 20:00 UTC on 31 December is 01:00 on 1 January in Pakistan
    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id,
        now=datetime(2026, 12, 31, 20, 0, tzinfo=UTC),
    )
    assert sale.invoice_number == "INV-2027-0001"


# --- credit -------------------------------------------------------------

def test_credit_sale_posts_a_ledger_entry_and_updates_the_balance(counter, user, milk):
    cust = Customer(name="Bilal", balance_paisa=5_000)
    db.session.add(cust)
    db.session.commit()

    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="credit", user_id=user.id, customer_id=cust.id, now=JAN_2026,
    )

    entry = db.session.query(CreditLedgerEntry).filter_by(sale_id=sale.id).one()
    assert entry.entry_type == "credit_sale"
    assert entry.amount_paisa == 56_000
    assert entry.balance_after_paisa == 61_000
    assert cust.balance_paisa == 61_000
    assert sale.amount_tendered_paisa is None and sale.change_paisa is None


def test_credit_sale_without_a_customer_is_refused(counter, user, milk):
    with pytest.raises(sales_service.PaymentError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="credit", user_id=user.id, now=JAN_2026,
        )


# --- atomicity --------------------------------------------------------

def test_a_failure_mid_sale_leaves_no_partial_state(counter, user, milk, chana):
    # chana has 10_000 milli; ask for 12_000 on the second line
    with pytest.raises(inv.InsufficientStockError):
        sales_service.record_sale(
            lines=[
                CartLine(product=milk, quantity_milli=3_000, unit_price_paisa=28_000,
                         quantity_source="stepper"),
                CartLine(product=chana, quantity_milli=12_000, unit_price_paisa=48_000,
                         quantity_source="manual_weight"),
            ],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )

    assert db.session.query(Sale).count() == 0
    assert db.session.query(SaleItem).count() == 0
    assert db.session.query(StockMovement).filter_by(movement_type="sale").count() == 0
    assert milk.stock_quantity_milli == 20_000  # the first line did not stick
    assert chana.stock_quantity_milli == 10_000

    # and the invoice number it briefly claimed is released — no gap
    good = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    assert good.invoice_number == "INV-2026-0001"


# --- cart / payment guards -------------------------------------------

def test_checkout_is_blocked_on_an_empty_cart(counter, user):
    with pytest.raises(sales_service.EmptyCartError):
        sales_service.record_sale(
            lines=[], payment_method="cash", user_id=user.id, now=JAN_2026
        )


def test_cash_tendered_below_the_total_is_refused(counter, user, milk):
    with pytest.raises(sales_service.PaymentError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="cash", user_id=user.id, amount_tendered_paisa=10_000,
            now=JAN_2026,
        )


# --- weighed-item entry (ADR-0005 / ADR-0007) -----------------------

def test_by_amount_line_stores_the_typed_amount_and_the_source(counter, user, chana):
    sale = sales_service.record_sale(
        lines=[CartLine(product=chana, quantity_milli=417, unit_price_paisa=48_000,
                        quantity_source="manual_amount", typed_amount_paisa=20_000)],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    item = db.session.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert item.line_total_paisa == 20_000  # exactly what was typed, not 20_016
    assert item.quantity_source == "manual_amount"
    assert item.quantity_milli == 417
    assert chana.stock_quantity_milli == 10_000 - 417  # stock follows the weight


def test_a_sealed_pack_cannot_be_sold_by_amount(counter, user, milk):
    # a whole-unit quantity, so it is the by-amount rule that rejects it,
    # not the fractional-quantity guard
    with pytest.raises(sales_service.CartLineError, match="by-amount"):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                            quantity_source="manual_amount", typed_amount_paisa=14_000)],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )


def test_a_line_with_no_quantity_is_refused(counter, user, milk):
    with pytest.raises(sales_service.CartLineError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=0, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )


def test_an_unknown_quantity_source_is_refused(counter, user, milk):
    with pytest.raises(sales_service.CartLineError, match="quantity source"):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                            quantity_source="telepathy")],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )


def test_an_unknown_payment_method_is_refused(counter, user, milk):
    with pytest.raises(sales_service.PaymentError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="barter", user_id=user.id, now=JAN_2026,
        )


def test_a_credit_sale_to_a_missing_customer_is_refused(counter, user, milk):
    with pytest.raises(sales_service.PaymentError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="credit", user_id=user.id, customer_id=999, now=JAN_2026,
        )


def test_a_card_sale_moves_no_cash_and_writes_no_ledger(counter, user, milk):
    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="card", user_id=user.id, now=JAN_2026,
    )
    assert sale.payment_method == "card"
    assert sale.amount_tendered_paisa is None and sale.change_paisa is None
    assert db.session.query(CreditLedgerEntry).count() == 0


def test_a_sale_bootstraps_the_invoice_counter_when_it_is_missing(user, milk):
    # note: no `counter` fixture — the row does not exist yet
    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    assert sale.invoice_number == "INV-2026-0001"


def test_a_sealed_pack_cannot_be_sold_fractionally(counter, user, milk):
    with pytest.raises(sales_service.CartLineError):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=1_500, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )


def test_a_typed_amount_that_is_not_a_whole_rupee_is_refused(counter, user, chana):
    with pytest.raises(sales_service.CartLineError):
        sales_service.record_sale(
            lines=[CartLine(product=chana, quantity_milli=100, unit_price_paisa=48_000,
                            quantity_source="manual_amount", typed_amount_paisa=20_050)],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )


def test_persisted_money_columns_are_whole_rupees(counter, user, chana):
    sale = sales_service.record_sale(
        lines=[CartLine(product=chana, quantity_milli=333, unit_price_paisa=48_000,
                        quantity_source="manual_weight")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    assert sale.subtotal_paisa % 100 == 0
    assert sale.total_paisa % 100 == 0
    item = db.session.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert item.line_total_paisa % 100 == 0


# --- never-counted products: found at the till (ADR-0025) --------------------

def test_a_never_counted_product_books_its_shortfall_as_found_then_sells(counter, user):
    biscuits = inv.create_product(name="Local Biscuits", sell_price_paisa=8_000)
    sale = sales_service.record_sale(
        lines=[CartLine(product=biscuits, quantity_milli=3_000, unit_price_paisa=8_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    moves = (db.session.query(StockMovement).filter_by(product_id=biscuits.id)
             .order_by(StockMovement.id).all())
    assert [(m.movement_type, m.quantity_delta_milli) for m in moves] == [
        ("stock_in", 3_000), ("sale", -3_000)]
    found = moves[0]
    assert found.reference_type == inv.FOUND_AT_TILL and found.reference_id == sale.id
    assert found.created_by_user_id == user.id and sale.invoice_number in found.reason
    db.session.expire(biscuits)
    assert biscuits.stock_quantity_milli == 0  # a truthful zero, not negative


def test_found_stock_never_makes_a_product_counted(counter, user):
    biscuits = inv.create_product(name="Local Biscuits", sell_price_paisa=8_000)
    for _ in range(2):  # the second sale must not be capped by the first's booking
        sales_service.record_sale(
            lines=[CartLine(product=biscuits, quantity_milli=1_000, unit_price_paisa=8_000,
                            quantity_source="stepper")],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )
    assert biscuits.id not in inv.counted_product_ids([biscuits.id])
    assert db.session.query(Sale).count() == 2


def test_two_loose_lines_of_an_uncounted_product_book_one_shortfall(counter, user):
    loose = inv.create_product(name="Loose Daal", sell_price_paisa=30_000,
                               allows_fractional=True, unit_label="kg")
    sales_service.record_sale(
        lines=[CartLine(product=loose, quantity_milli=500, unit_price_paisa=30_000,
                        quantity_source="manual_weight"),
               CartLine(product=loose, quantity_milli=750, unit_price_paisa=30_000,
                        quantity_source="manual_weight")],
        payment_method="cash", user_id=user.id, now=JAN_2026,
    )
    found = db.session.query(StockMovement).filter_by(
        product_id=loose.id, reference_type=inv.FOUND_AT_TILL).all()
    assert [m.quantity_delta_milli for m in found] == [1_250]


def test_a_counted_product_is_still_refused_not_found(counter, user, milk):
    # milk was stocked in (counted): short stock is a refusal, never a silent booking
    with pytest.raises(inv.InsufficientStockError, match="Olpers Milk 1L"):
        sales_service.record_sale(
            lines=[CartLine(product=milk, quantity_milli=999_000, unit_price_paisa=28_000,
                            quantity_source="stepper")],
            payment_method="cash", user_id=user.id, now=JAN_2026,
        )
    assert db.session.query(StockMovement).filter_by(reference_type=inv.FOUND_AT_TILL).count() == 0
