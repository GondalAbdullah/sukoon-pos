"""The Till — cart, quantity entry, payment, Sale Complete (Development
Specification Phase 3; edge-case matrix 'POS / Billing' and 'Weighed-item entry')."""
from __future__ import annotations

import pytest

from sukoon.extensions import db
from sukoon.models import Customer, Sale
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from tests.conftest import CASHIER_PASSWORD


@pytest.fixture
def till(client, seeded, login):
    seed_invoice_counter()
    login("T1", CASHIER_PASSWORD)
    return client


@pytest.fixture
def milk(app, seeded):
    p = inv.create_product(name="Olpers Milk 1L", sell_price_paisa=28_000)
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=50_000,
        reason="in", user_id=seeded["admin"].id,
    )
    return p


@pytest.fixture
def atta(app, seeded):
    p = inv.create_product(
        name="Chakki Atta loose", sell_price_paisa=12_000,
        allows_fractional=True, unit_label="kg",
    )
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=100_000,
        reason="in", user_id=seeded["admin"].id,
    )
    return p


def _add(client, **data):
    return client.post("/till/add", data=data, follow_redirects=True)


# --- loading -----------------------------------------------------------

def test_cashier_can_open_the_till(till):
    assert till.get("/till/").status_code == 200


def test_the_till_requires_a_login(client):
    resp = client.get("/till/", follow_redirects=False)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


# --- building the cart ----------------------------------------------

def test_a_sealed_pack_is_added_with_a_stepper_quantity(till, milk):
    _add(till, product_id=milk.id)
    with till.session_transaction() as s:
        assert s["cart"][0]["quantity_milli"] == 1_000
        assert s["cart"][0]["quantity_source"] == "stepper"


def test_adding_the_same_sealed_pack_bumps_the_stepper(till, milk):
    _add(till, product_id=milk.id)
    _add(till, product_id=milk.id)
    with till.session_transaction() as s:
        assert len(s["cart"]) == 1
        assert s["cart"][0]["quantity_milli"] == 2_000


def test_the_stepper_increments_and_decrements(till, milk):
    _add(till, product_id=milk.id)
    till.post("/till/line/0", data={"op": "inc"}, follow_redirects=True)
    with till.session_transaction() as s:
        assert s["cart"][0]["quantity_milli"] == 2_000
    till.post("/till/line/0", data={"op": "dec"}, follow_redirects=True)
    till.post("/till/line/0", data={"op": "dec"}, follow_redirects=True)
    with till.session_transaction() as s:
        assert s["cart"] == []  # dropped at zero


def test_an_unknown_code_offers_provisional_creation(till):
    # a Cashier holds product.create_provisional, so an unknown code is not a
    # dead end — it offers inline creation (ADR-0011 §2)
    resp = _add(till, code="8964999999999")
    assert b"isn" in resp.data and b"catalogue yet" in resp.data
    with till.session_transaction() as s:
        assert s.get("cart", []) == []  # nothing added until the form is submitted


def test_cashier_creates_a_provisional_product_at_the_till(till, seeded):
    resp = till.post(
        "/till/new",
        data={"code": "8964999999999", "name": "Local Biscuits", "sell_price": "80"},
        follow_redirects=True,
    )
    assert b"needs completing later" in resp.data

    rows, total = inv.list_products(query="Local Biscuits")
    assert total == 1
    product = rows[0]
    assert product.is_provisional is True
    assert product.created_by_user_id == seeded["cashier"].id
    assert inv.resolve_barcode("8964999999999").product.id == product.id

    needs, _ = inv.list_products(needs_completing=True)
    assert product.id in {p.id for p in needs}
    with till.session_transaction() as s:
        assert s["cart"][0]["product_id"] == product.id


def test_provisional_create_needs_a_name_and_price(till):
    resp = till.post(
        "/till/new", data={"code": "x", "name": "", "sell_price": "10"},
        follow_redirects=True,
    )
    assert b"name is required" in resp.data
    assert inv.list_products()[1] == 0


def test_a_barcode_resolves_to_its_product(till, milk, seeded):
    inv.assign_barcode(product=milk, code="8964000000123", user_id=seeded["admin"].id)
    _add(till, code="8964000000123")
    with till.session_transaction() as s:
        assert s["cart"][0]["product_id"] == milk.id


# --- loose goods (ADR-0005) ---------------------------------------

def test_a_loose_item_is_added_needing_a_weight(till, atta):
    _add(till, product_id=atta.id)
    with till.session_transaction() as s:
        assert s["cart"][0]["quantity_milli"] is None
    # checkout is blocked while it is unweighed
    resp = till.post("/till/checkout", data={"payment_method": "cash"}, follow_redirects=True)
    assert b"needs a weight" in resp.data
    assert db.session.query(Sale).count() == 0


def test_setting_a_weight_makes_the_line_ready(till, atta):
    _add(till, product_id=atta.id)
    till.post("/till/line/0", data={"op": "set_weight", "weight": "1.5"}, follow_redirects=True)
    with till.session_transaction() as s:
        assert s["cart"][0]["quantity_milli"] == 1_500
        assert s["cart"][0]["quantity_source"] == "manual_weight"


def test_setting_an_amount_stores_the_typed_rupees_and_derives_the_weight(till, atta):
    _add(till, product_id=atta.id)
    till.post("/till/line/0", data={"op": "set_amount", "amount": "200"}, follow_redirects=True)
    with till.session_transaction() as s:
        row = s["cart"][0]
        assert row["typed_amount_paisa"] == 20_000
        assert row["quantity_source"] == "manual_amount"
        # Rs 200 / Rs 120/kg = 1.6667 kg, half-up to the milli -> 1667
        assert row["quantity_milli"] == 1_667


# --- checkout --------------------------------------------------

def test_a_cash_sale_completes_and_clears_the_cart(till, milk):
    _add(till, product_id=milk.id)
    _add(till, product_id=milk.id)
    resp = till.post(
        "/till/checkout",
        data={"payment_method": "cash", "amount_tendered": "1000"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Sale complete" in resp.data
    assert b"INV-" in resp.data

    sale = db.session.query(Sale).one()
    assert sale.total_paisa == 56_000
    assert sale.change_paisa == 100_000 - 56_000
    db.session.expire(milk)
    assert milk.stock_quantity_milli == 50_000 - 2_000
    with till.session_transaction() as s:
        assert s.get("cart", []) == []


def test_an_empty_cart_cannot_be_checked_out(till):
    resp = till.post("/till/checkout", data={"payment_method": "cash"}, follow_redirects=True)
    assert b"cart is empty" in resp.data
    assert db.session.query(Sale).count() == 0


def test_a_credit_sale_needs_a_customer_id(till, milk):
    _add(till, product_id=milk.id)
    resp = till.post(
        "/till/checkout", data={"payment_method": "credit"}, follow_redirects=True
    )
    assert b"needs a customer" in resp.data
    assert db.session.query(Sale).count() == 0


def test_a_credit_sale_to_a_real_customer_completes(till, milk):
    cust = Customer(name="Bilal", balance_paisa=0)
    db.session.add(cust)
    db.session.commit()
    _add(till, product_id=milk.id)
    resp = till.post(
        "/till/checkout",
        data={"payment_method": "credit", "customer_id": str(cust.id)},
        follow_redirects=True,
    )
    assert b"Sale complete" in resp.data
    db.session.expire(cust)
    assert cust.balance_paisa == 28_000


def test_clear_empties_the_cart(till, milk):
    _add(till, product_id=milk.id)
    till.post("/till/clear", follow_redirects=True)
    with till.session_transaction() as s:
        assert s.get("cart", []) == []


# --- more edges -----------------------------------------------------

def test_add_by_a_unique_name_fragment(till, milk):
    resp = _add(till, code="Olpers")
    assert resp.status_code == 200
    with till.session_transaction() as s:
        assert s["cart"][0]["product_id"] == milk.id


def test_remove_line_drops_the_row(till, milk, atta):
    _add(till, product_id=milk.id)
    _add(till, product_id=atta.id)
    till.post("/till/line/0", data={"op": "remove"}, follow_redirects=True)
    with till.session_transaction() as s:
        assert len(s["cart"]) == 1
        assert s["cart"][0]["product_id"] == atta.id


def test_update_line_out_of_range_is_404(till):
    assert till.post("/till/line/5", data={"op": "remove"}).status_code == 404


def test_stepper_ops_are_rejected_on_a_loose_line(till, atta):
    _add(till, product_id=atta.id)
    assert till.post("/till/line/0", data={"op": "inc"}).status_code == 400


def test_a_blank_weight_is_reported(till, atta):
    _add(till, product_id=atta.id)
    resp = till.post(
        "/till/line/0", data={"op": "set_weight", "weight": "abc"}, follow_redirects=True
    )
    assert b"Enter a weight" in resp.data


def test_checkout_is_blocked_when_stock_is_short(till, milk, seeded):
    inv.apply_stock_movement(
        product=milk, movement_type="correction", quantity_milli=1_000,
        reason="recount", user_id=seeded["admin"].id,
    )
    _add(till, product_id=milk.id)
    _add(till, product_id=milk.id)  # cart wants 2, only 1 in stock
    resp = till.post(
        "/till/checkout",
        data={"payment_method": "cash", "amount_tendered": "1000"},
        follow_redirects=True,
    )
    assert b"in stock" in resp.data
    assert db.session.query(Sale).count() == 0
    db.session.expire(milk)
    assert milk.stock_quantity_milli == 1_000  # untouched


def test_a_by_amount_loose_sale_completes_and_drops_the_derived_weight(till, atta):
    _add(till, product_id=atta.id)
    till.post("/till/line/0", data={"op": "set_amount", "amount": "240"}, follow_redirects=True)
    resp = till.post(
        "/till/checkout",
        data={"payment_method": "cash", "amount_tendered": "240"},
        follow_redirects=True,
    )
    assert b"Sale complete" in resp.data
    sale = db.session.query(Sale).one()
    item = sale.items[0]
    assert item.line_total_paisa == 24_000  # exactly what was typed
    assert item.quantity_source == "manual_amount"
    db.session.expire(atta)
    assert atta.stock_quantity_milli == 100_000 - item.quantity_milli


def test_the_complete_page_is_shown_after_a_sale(till, milk):
    _add(till, product_id=milk.id)
    till.post(
        "/till/checkout",
        data={"payment_method": "card"},
        follow_redirects=True,
    )
    sale = db.session.query(Sale).one()
    resp = till.get(f"/till/complete/{sale.id}")
    assert resp.status_code == 200
    assert sale.invoice_number.encode() in resp.data
    assert till.get("/till/complete/9999").status_code == 404


# --- till terminal identity (ADR-0023) --------------------------------

def test_a_fresh_till_is_asked_to_name_itself(till):
    resp = till.get("/till/")
    assert b"Name this till" in resp.data


def test_naming_a_till_sets_a_cookie_and_stops_asking(till):
    resp = till.post("/till/terminal", data={"label": "Till 2"}, follow_redirects=True)
    assert b"Name this till" not in resp.data
    assert b"Till 2" in resp.data
    assert till.get_cookie("sukoon_terminal").value.strip('"') == "Till 2"


def test_a_sale_rung_up_after_naming_carries_the_terminal_label(till, milk):
    till.post("/till/terminal", data={"label": "Till 2"}, follow_redirects=True)
    _add(till, product_id=milk.id)
    till.post("/till/checkout", data={"payment_method": "card"}, follow_redirects=True)
    sale = db.session.query(Sale).one()
    assert sale.terminal_label == "Till 2"


def test_a_sale_before_naming_has_no_terminal_label(till, milk):
    _add(till, product_id=milk.id)
    till.post("/till/checkout", data={"payment_method": "card"}, follow_redirects=True)
    sale = db.session.query(Sale).one()
    assert sale.terminal_label is None


def test_renaming_a_till_only_affects_future_sales(till, milk):
    till.post("/till/terminal", data={"label": "Till 1"}, follow_redirects=True)
    _add(till, product_id=milk.id)
    till.post("/till/checkout", data={"payment_method": "card"}, follow_redirects=True)

    till.post("/till/terminal", data={"label": "Till 1 (front counter)"}, follow_redirects=True)
    _add(till, product_id=milk.id)
    till.post("/till/checkout", data={"payment_method": "card"}, follow_redirects=True)

    labels = sorted(s.terminal_label for s in db.session.query(Sale).all())
    assert labels == ["Till 1", "Till 1 (front counter)"]


def test_a_blank_label_does_not_overwrite_an_existing_name(till, milk):
    till.post("/till/terminal", data={"label": "Till 2"}, follow_redirects=True)
    till.post("/till/terminal", data={"label": "   "}, follow_redirects=True)
    assert till.get_cookie("sukoon_terminal").value.strip('"') == "Till 2"
