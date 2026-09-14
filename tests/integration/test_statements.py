"""Khata statement (Development Spec Phase 4 step 4; DoD: "statement output matches
an expected fixture for a known scenario"). The fixtures in tests/fixtures/ were
written by hand from the scenario below before the code was run against them."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Payment, Refund, Sale
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import refund_service, sales_service, statements
from sukoon.services.refund_service import RefundLineSpec
from sukoon.services.sales_service import CartLine
from tests.conftest import CASHIER_PASSWORD

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _pin(entry_type, when, customer):
    """Give the newest ledger entry of a type (and its sale/payment) a fixed time."""
    e = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.customer_id == customer.id,
                                           CreditLedgerEntry.entry_type == entry_type)
        .order_by(CreditLedgerEntry.id.desc()))
    e.created_at = when
    if e.sale_id and entry_type == "credit_sale":
        db.session.get(Sale, e.sale_id).created_at = when
    if e.payment_id:
        db.session.get(Payment, e.payment_id).created_at = when
    db.session.commit()


@pytest.fixture
def usman(seeded):
    seed_invoice_counter()
    cashier, admin = seeded["cashier"], seeded["admin"]
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=ghee, movement_type="stock_in", quantity_milli=100_000,
                             reason="in", user_id=admin.id)
    c = khata.create_customer(name="Haji Muhammad Usman", phone_raw="0300 5541298",
                              user_id=cashier.id)

    def sell(units, when):
        return sales_service.record_sale(
            lines=[CartLine(product=ghee, quantity_milli=units * 1000, unit_price_paisa=60_000,
                            quantity_source="stepper")],
            payment_method="credit", customer_id=c.id, user_id=cashier.id, now=when)

    t1 = datetime(2026, 9, 2, 7, 15, tzinfo=UTC)     # 12:15 PKT
    sell(10, t1)
    _pin("credit_sale", t1, c)
    t2 = datetime(2026, 9, 10, 11, 0, tzinfo=UTC)    # 16:00 PKT
    khata.record_payment(customer_id=c.id, amount_paisa=200_000, method="cash",
                         received_by_user_id=cashier.id)
    _pin("payment", t2, c)
    t3 = datetime(2026, 9, 30, 20, 30, tzinfo=UTC)   # 01:30 PKT on 1 October
    sale = sell(5, t3)
    _pin("credit_sale", t3, c)
    t4 = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)     # 11:00 PKT
    r = refund_service.initiate_refund(
        sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1000)],
        reason="one jar dented", initiated_by_user_id=cashier.id)
    refund_service.approve_refund(refund_id=r.id, approved_by_user_id=admin.id)
    _pin("refund", t4, c)
    t5 = datetime(2026, 10, 20, 9, 45, tzinfo=UTC)   # 14:45 PKT, Rs 600 over
    khata.record_payment(customer_id=c.id, amount_paisa=700_000, method="mobile_wallet",
                         reference="TX-5521", received_by_user_id=cashier.id,
                         allow_overpayment=True)
    _pin("payment", t5, c)
    assert db.session.get(Refund, r.id).id == 1
    return c


@pytest.mark.parametrize("period,fixture", [
    ("2026-10", "khata_statement_october_2026.txt"),
    ("2026-09", "khata_statement_september_2026.txt"),
])
def test_statement_matches_the_hand_written_fixture(usman, period, fixture):
    doc = statements.build_statement(usman, statements.period_for(period))
    expected = (FIXTURES / fixture).read_text().strip().split("\n")
    assert statements.statement_text(doc) == expected
    assert doc.reconciles


def test_a_purchase_at_1am_on_the_1st_is_in_the_new_month(usman):
    # the month/timezone boundary edge case: 20:30 UTC on 30 Sept is 1 Oct in Pakistan
    sept = statements.build_statement(usman, statements.period_for("2026-09"))
    assert all("INV-2026-0002" not in ln.details for ln in sept.lines)


def test_an_all_time_statement_runs_from_settled_to_the_current_balance(usman):
    doc = statements.build_statement(usman, statements.period_for("all"))
    assert doc.opening == "Settled" and doc.closing == "Rs 600 in credit" and len(doc.lines) == 5


def test_an_empty_period_says_so_and_carries_the_balance(usman):
    doc = statements.build_statement(usman, statements.period_for("2026-11"))
    text = statements.statement_text(doc)
    assert "No purchases or payments in this period." in text
    assert doc.opening == doc.closing == "Rs 600 in credit"


def test_a_nonsense_period_falls_back_to_the_current_month(usman):
    assert statements.period_for("banana").key == statements.period_for(None).key


def test_the_pdf_renders_and_paginates_a_long_history(seeded):
    seed_invoice_counter()
    c = khata.create_customer(name="Long History", phone_raw=None, user_id=seeded["cashier"].id)
    for _ in range(90):  # well past one A4 page of rows
        khata.record_payment(customer_id=c.id, amount_paisa=100, method="cash",
                             received_by_user_id=seeded["cashier"].id, allow_overpayment=True)
    pdf = statements.render_pdf(statements.build_statement(c, statements.period_for("all")))
    assert pdf.startswith(b"%PDF-")
    pages = re.findall(rb"/Type\s*/Page(?!s)", pdf)
    assert len(pages) >= 2


def test_pdf_export_route_for_any_staff(client, seeded, login, usman):
    login("T1", CASHIER_PASSWORD)
    resp = client.get(f"/khata/{usman.id}/statement.pdf?period=2026-10")
    assert resp.status_code == 200 and resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF-")
