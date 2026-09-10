"""Returns and refunds (Development Specification Phase 3 step 6; ADR-0020
consequential test cases; edge-case matrix 'POS / Billing')."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Customer, Sale, StockMovement, User
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import refund_service, sales_service
from sukoon.services.auth_service import hash_password
from sukoon.services.refund_service import RefundLineSpec
from sukoon.services.sales_service import CartLine
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

JAN = datetime(2026, 1, 10, tzinfo=UTC)


@pytest.fixture
def staff(app):
    a = User(name="Boss", initials="BO", role="admin", password_hash=hash_password("x"))
    c = User(name="Till", initials="TL", role="cashier", password_hash=hash_password("x"))
    db.session.add_all([a, c])
    db.session.commit()
    return {"admin": a, "cashier": c}


@pytest.fixture
def milk(app, staff):
    p = inv.create_product(name="Milk 1L", sell_price_paisa=28_000)
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=40_000,
        reason="in", user_id=staff["admin"].id,
    )
    return p


@pytest.fixture
def rice(app, staff):
    p = inv.create_product(
        name="Rice loose", sell_price_paisa=16_000, allows_fractional=True, unit_label="kg"
    )
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=100_000,
        reason="in", user_id=staff["admin"].id,
    )
    return p


def _cash_sale(staff, *lines) -> Sale:
    seed_invoice_counter()
    return sales_service.record_sale(
        lines=list(lines), payment_method="cash", user_id=staff["cashier"].id,
        amount_tendered_paisa=1_000_000, now=JAN,
    )


# --- initiate ---------------------------------------------------------

def test_initiate_records_a_pending_refund_and_moves_nothing(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=3_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    milk_stock = milk.stock_quantity_milli

    refund = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
        reason="wrong item",
        initiated_by_user_id=staff["cashier"].id,
    )
    assert refund.status == "pending_approval"
    assert refund.total_paisa == 28_000
    assert refund.method == "cash"
    db.session.expire(milk)
    assert milk.stock_quantity_milli == milk_stock  # nothing moved yet
    assert db.session.query(Sale).one().status == "completed"


def test_a_reason_is_required(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    with pytest.raises(refund_service.RefundError):
        refund_service.initiate_refund(
            sale_id=sale.id,
            lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
            reason="  ",
            initiated_by_user_id=staff["cashier"].id,
        )


def test_a_line_cannot_be_over_refunded(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    with pytest.raises(refund_service.RefundLineError):
        refund_service.initiate_refund(
            sale_id=sale.id,
            lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=3_000)],
            reason="x", initiated_by_user_id=staff["cashier"].id,
        )


def test_a_pending_refund_reserves_the_quantity(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    si = sale.items[0].id
    refund_service.initiate_refund(
        sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=si, quantity_milli=2_000)],
        reason="x", initiated_by_user_id=staff["cashier"].id,
    )
    with pytest.raises(refund_service.RefundLineError):
        refund_service.initiate_refund(
            sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=si, quantity_milli=1_000)],
            reason="again", initiated_by_user_id=staff["cashier"].id,
        )


def test_a_by_amount_line_is_whole_or_nothing(staff, rice):
    sale = _cash_sale(
        staff,
        CartLine(product=rice, quantity_milli=1_250, unit_price_paisa=16_000,
                 quantity_source="manual_amount", typed_amount_paisa=20_000),
    )
    si = sale.items[0].id
    with pytest.raises(refund_service.RefundLineError):
        refund_service.initiate_refund(
            sale_id=sale.id,
            lines=[RefundLineSpec(sale_item_id=si, quantity_milli=600)],
            reason="partial", initiated_by_user_id=staff["cashier"].id,
        )
    refund = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=si, quantity_milli=1_250)],
        reason="whole", initiated_by_user_id=staff["cashier"].id,
    )
    assert refund.total_paisa == 20_000  # exactly what the customer paid


# --- approve --------------------------------------------------------

def test_approving_restocks_and_completes_the_status_transition(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=4_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    start = milk.stock_quantity_milli
    si = sale.items[0].id

    r1 = refund_service.initiate_refund(
        sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=si, quantity_milli=1_000)],
        reason="one back", initiated_by_user_id=staff["cashier"].id,
    )
    refund_service.approve_refund(refund_id=r1.id, approved_by_user_id=staff["admin"].id)
    db.session.expire(milk)
    assert milk.stock_quantity_milli == start + 1_000
    assert db.session.get(Sale, sale.id).status == "partially_refunded"

    r2 = refund_service.initiate_refund(
        sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=si, quantity_milli=3_000)],
        reason="rest back", initiated_by_user_id=staff["cashier"].id,
    )
    refund_service.approve_refund(refund_id=r2.id, approved_by_user_id=staff["admin"].id)
    db.session.expire(milk)
    assert milk.stock_quantity_milli == start + 4_000
    assert db.session.get(Sale, sale.id).status == "refunded"


def test_a_damaged_line_is_not_restocked(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    start = milk.stock_quantity_milli
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=2_000,
                              restock=False)],
        reason="leaked", initiated_by_user_id=staff["cashier"].id,
    )
    refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)
    db.session.expire(milk)
    assert milk.stock_quantity_milli == start  # not put back
    assert db.session.query(StockMovement).filter_by(movement_type="refund").count() == 0


def test_a_credit_sale_refund_reverses_the_ledger_and_moves_no_cash(staff, milk):
    seed_invoice_counter()
    cust = Customer(name="Adnan", balance_paisa=0)
    db.session.add(cust)
    db.session.commit()
    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="credit", user_id=staff["cashier"].id, customer_id=cust.id, now=JAN,
    )
    assert cust.balance_paisa == 56_000

    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
        reason="one back", initiated_by_user_id=staff["cashier"].id,
    )
    assert r.method == "credit_ledger"
    refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)

    entry = db.session.query(CreditLedgerEntry).filter_by(entry_type="refund").one()
    assert entry.amount_paisa == -28_000
    db.session.expire(cust)
    assert cust.balance_paisa == 28_000


def test_approve_is_idempotent_guarded(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
        reason="x", initiated_by_user_id=staff["cashier"].id,
    )
    refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)
    with pytest.raises(refund_service.RefundStateError):
        refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)


def test_a_failure_during_approval_leaves_the_refund_pending(staff, milk, monkeypatch):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    start = milk.stock_quantity_milli
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=2_000)],
        reason="x", initiated_by_user_id=staff["cashier"].id,
    )

    def boom(*a, **kw):
        raise RuntimeError("disk fell over")

    monkeypatch.setattr(refund_service.inventory_service, "apply_stock_movement", boom)
    with pytest.raises(RuntimeError):
        refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)

    db.session.expire_all()
    assert db.session.get(Sale, sale.id).status == "completed"
    assert refund_service.list_pending()[0].id == r.id  # still pending
    assert milk.stock_quantity_milli == start
    assert db.session.query(CreditLedgerEntry).count() == 0


def test_a_line_from_another_sale_is_refused(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    with pytest.raises(refund_service.RefundLineError):
        refund_service.initiate_refund(
            sale_id=sale.id,
            lines=[RefundLineSpec(sale_item_id=9_999, quantity_milli=1_000)],
            reason="x", initiated_by_user_id=staff["cashier"].id,
        )


def test_a_zero_quantity_line_is_refused(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    with pytest.raises(refund_service.RefundLineError):
        refund_service.initiate_refund(
            sale_id=sale.id,
            lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=0)],
            reason="x", initiated_by_user_id=staff["cashier"].id,
        )


def test_rejecting_a_refund_moves_nothing_and_cannot_be_repeated(staff, milk):
    sale = _cash_sale(
        staff,
        CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                 quantity_source="stepper"),
    )
    start = milk.stock_quantity_milli
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=2_000)],
        reason="mistake", initiated_by_user_id=staff["cashier"].id,
    )
    refund_service.reject_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)

    db.session.expire(milk)
    assert milk.stock_quantity_milli == start
    assert db.session.get(Sale, sale.id).status == "completed"
    assert refund_service.list_pending() == []
    # the rejected quantity is refundable again
    again = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=2_000)],
        reason="for real", initiated_by_user_id=staff["cashier"].id,
    )
    assert again.total_paisa == 56_000
    with pytest.raises(refund_service.RefundStateError):
        refund_service.reject_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)


def test_missing_refund_and_sale_are_calm_errors(staff):
    with pytest.raises(refund_service.RefundError):
        refund_service.approve_refund(refund_id=999, approved_by_user_id=staff["admin"].id)
    with pytest.raises(refund_service.RefundError):
        refund_service.reject_refund(refund_id=999, approved_by_user_id=staff["admin"].id)
    with pytest.raises(refund_service.RefundError):
        refund_service.initiate_refund(
            sale_id=999, lines=[RefundLineSpec(sale_item_id=1, quantity_milli=1)],
            reason="x", initiated_by_user_id=staff["cashier"].id,
        )


def test_the_refund_screens_render(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=seeded["admin"].id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=15_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id, now=JAN,
    )
    login("T1", CASHIER_PASSWORD)
    assert client.get(f"/refunds/find?invoice={sale.invoice_number}").status_code == 200
    assert client.get("/refunds/find?invoice=INV-2099-9999").status_code == 200  # not found, calm
    assert client.get(f"/refunds/sale/{sale.id}").status_code == 200
    client.post("/logout")
    login("Owner", ADMIN_PASSWORD)
    assert client.get("/refunds/pending").status_code == 200


def test_line_totals_mirror_the_sale(staff, rice):
    # 0.333 kg at Rs 160/kg -> Rs 53.28 -> Rs 53 on the sale; the refund matches
    sale = _cash_sale(
        staff,
        CartLine(product=rice, quantity_milli=333, unit_price_paisa=16_000,
                 quantity_source="manual_weight"),
    )
    sale_line_total = sale.items[0].line_total_paisa
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=333)],
        reason="x", initiated_by_user_id=staff["cashier"].id,
    )
    assert r.items[0].line_total_paisa == sale_line_total


# --- routes / authorization (ADR-0020) -----------------------------

def test_cashier_can_initiate_but_not_approve(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=seeded["admin"].id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=15_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id, now=JAN,
    )

    login("T1", CASHIER_PASSWORD)
    resp = client.post("/refunds", data={
        "sale_id": sale.id, f"qty_{sale.items[0].id}": "1", "reason": "changed mind",
    }, follow_redirects=True)
    assert b"waiting for an Admin" in resp.data

    refund = refund_service.list_pending()[0]
    # a cashier hitting the approve route is refused
    assert client.post(f"/refunds/{refund.id}/approve",
                       data={"step_up_password": CASHIER_PASSWORD}).status_code == 403


def test_admin_can_reject_a_pending_refund_via_the_route(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=seeded["admin"].id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=15_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id, now=JAN,
    )
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
        reason="x", initiated_by_user_id=seeded["cashier"].id,
    )
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(f"/refunds/{r.id}/reject", follow_redirects=True)
    assert b"Refund rejected" in resp.data
    assert refund_service.list_pending() == []
    # approving it now is a calm error, surfaced as a flash not a crash
    resp = client.post(f"/refunds/{r.id}/approve",
                       data={"step_up_password": ADMIN_PASSWORD}, follow_redirects=True)
    assert b"already rejected" in resp.data


def test_admin_approve_needs_a_valid_step_up_password(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=seeded["admin"].id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=15_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id, now=JAN,
    )
    r = refund_service.initiate_refund(
        sale_id=sale.id,
        lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1_000)],
        reason="x", initiated_by_user_id=seeded["cashier"].id,
    )

    login("Owner", ADMIN_PASSWORD)
    assert client.post(f"/refunds/{r.id}/approve",
                       data={"step_up_password": "wrong"}).status_code == 403
    resp = client.post(f"/refunds/{r.id}/approve",
                       data={"step_up_password": ADMIN_PASSWORD}, follow_redirects=True)
    assert b"Refund approved" in resp.data
