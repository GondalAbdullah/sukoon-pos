"""Khata screens and the till's Khata picker (Phase 4; ADR-0014, ADR-0026)."""
from __future__ import annotations

import pytest

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Customer, Payment, Sale, User
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


@pytest.fixture
def setup(client, seeded, login):
    seed_invoice_counter()
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=ghee, movement_type="stock_in", quantity_milli=500_000,
                             reason="in", user_id=seeded["admin"].id)
    return {"ghee": ghee, **seeded}


def _as(client, login, who):
    client.post("/logout")
    login(*({"cashier": ("T1", CASHIER_PASSWORD), "admin": ("Owner", ADMIN_PASSWORD)}[who]))


def _open(setup, name="Haji Usman", phone="0300 5541298"):
    return khata.create_customer(name=name, phone_raw=phone, user_id=setup["cashier"].id)


# --- screens + permissions -------------------------------------------------------

def test_a_cashier_opens_a_khata_through_the_form(client, login, setup):
    _as(client, login, "cashier")
    assert client.get("/khata/").status_code == 200
    resp = client.post("/khata/new", data={"name": "Haji Usman", "phone": "0300 5541298",
                                           "verify": "shown"}, follow_redirects=True)
    assert "Khata opened for Haji Usman." in resp.get_data(as_text=True)
    c = db.session.scalar(db.select(Customer))
    assert c.phone_verified_method == "shown" and c.credit_limit_paisa == 1_000_000


def test_the_form_asks_before_a_duplicate_number(client, login, setup):
    _open(setup)
    _as(client, login, "cashier")
    html = client.post("/khata/new", data={"name": "Usman Traders", "phone": "+923005541298"}
                       ).get_data(as_text=True)
    assert "already on Haji Usman's Khata. Same person?" in html
    assert db.session.query(Customer).count() == 1
    client.post("/khata/new", data={"name": "Usman Traders", "phone": "+923005541298",
                                    "confirm_duplicate": "1"})
    assert db.session.query(Customer).count() == 2


def test_only_an_admin_sets_limits_or_archives(client, login, setup):
    c = _open(setup)
    _as(client, login, "cashier")
    assert client.post(f"/khata/{c.id}/credit", data={"credit_limit": "50000"}).status_code == 403
    assert client.post(f"/khata/{c.id}/remove").status_code == 403
    assert "Credit (Admin)" not in client.get(f"/khata/{c.id}/edit").get_data(as_text=True)

    _as(client, login, "admin")
    client.post(f"/khata/{c.id}/credit", data={"credit_limit": "50000", "credit_terms_days": "30"})
    db.session.expire(c)
    assert (c.credit_limit_paisa, c.credit_terms_days) == (5_000_000, 30)
    client.post(f"/khata/{c.id}/credit", data={"no_limit": "1", "credit_terms_days": ""})
    db.session.expire(c)
    assert c.credit_limit_paisa is None and c.credit_terms_days is None


def test_recording_a_payment_and_an_overpayment_through_the_screen(client, login, setup):
    c = _open(setup)
    c.balance_paisa = 0
    db.session.commit()
    khata.post_entry(c, entry_type="credit_sale", amount_paisa=100_000, user_id=setup["admin"].id)
    db.session.commit()
    _as(client, login, "cashier")

    resp = client.post(f"/khata/{c.id}/payment", data={"amount": "400", "method": "cash"},
                       follow_redirects=True)
    assert "Payment recorded. Haji Usman: Rs 600 owed." in resp.get_data(as_text=True)

    html = client.post(f"/khata/{c.id}/payment",
                       data={"amount": "1000", "method": "bank_transfer", "reference": "HBL-7"}
                       ).get_data(as_text=True)
    assert "Rs 400 more than they owe" in html
    assert db.session.query(Payment).count() == 1  # not yet

    resp = client.post(f"/khata/{c.id}/payment", follow_redirects=True, data={
        "amount": "1000", "method": "bank_transfer", "reference": "HBL-7",
        "allow_overpayment": "1"})
    text = resp.get_data(as_text=True)
    assert "Rs 400 in credit" in text and "Rs -" not in text  # never a bare negative


def test_confirming_a_number_later(client, login, setup):
    c = _open(setup)
    _as(client, login, "cashier")
    client.post(f"/khata/{c.id}/verify", data={"verify": "called"})
    db.session.expire(c)
    assert c.phone_verified and c.phone_verified_by_user_id == setup["cashier"].id


def test_statement_page_renders_for_a_period(client, login, setup):
    c = _open(setup)
    _as(client, login, "cashier")
    assert client.get(f"/khata/{c.id}/statement?period=all").status_code == 200
    assert client.get(f"/khata/{c.id}/statement?period=2026-09").status_code == 200


def test_archiving_through_the_screen(client, login, setup):
    c = _open(setup)
    _as(client, login, "admin")
    resp = client.post(f"/khata/{c.id}/remove", follow_redirects=True)
    assert "Haji Usman was removed." in resp.get_data(as_text=True)


# --- the till's Khata picker (replaces the raw customer ID) -------------------------

def test_search_choose_and_sell_on_a_khata(client, login, setup):
    c = _open(setup)
    _as(client, login, "cashier")
    assert "Haji Usman" in client.get("/till/customers?q=usman").get_data(as_text=True)
    assert "Haji Usman" in client.get("/till/customers?q=0300-554-1298").get_data(as_text=True)
    client.post("/till/add", data={"product_id": setup["ghee"].id})
    html = client.post("/till/customer", data={"customer_id": c.id},
                       follow_redirects=True).get_data(as_text=True)
    assert "on their Khata" in html and "Balance after this sale" in html
    resp = client.post("/till/checkout", data={"payment_method": "credit"}, follow_redirects=True)
    assert b"Sale complete" in resp.data
    db.session.expire(c)
    assert c.balance_paisa == 60_000
    with client.session_transaction() as s:
        assert "till_customer_id" not in s  # the next sale starts as a walk-in


def test_opening_a_khata_from_the_till_comes_straight_back_chosen(client, login, setup):
    _as(client, login, "cashier")
    resp = client.post("/khata/new", data={"name": "New Regular", "phone": "", "return": "till"})
    assert resp.status_code == 302 and resp.location.endswith("/till/")
    with client.session_transaction() as s:
        assert s["till_customer_id"] == db.session.scalar(db.select(Customer)).id


def _over_limit_cart(client, login, setup):
    c = _open(setup)
    khata.post_entry(c, entry_type="credit_sale", amount_paisa=960_000, user_id=setup["admin"].id)
    db.session.commit()
    _as(client, login, "cashier")
    client.post("/till/add", data={"product_id": setup["ghee"].id})  # Rs 600 -> Rs 10,200
    client.post("/till/customer", data={"customer_id": c.id})
    return c


def test_over_limit_is_blocked_at_the_till_for_a_cashier(client, login, setup):
    _over_limit_cart(client, login, setup)
    html = client.get("/till/").get_data(as_text=True)
    assert "Rs 200 over their limit" in html
    resp = client.post("/till/checkout", data={"payment_method": "credit"}, follow_redirects=True)
    assert "Rs 200 over their Rs 10,000 limit" in resp.get_data(as_text=True)
    assert db.session.query(Sale).count() == 0


def test_a_wrong_admin_password_is_refused_and_counted(client, login, setup):
    _over_limit_cart(client, login, setup)
    resp = client.post("/till/checkout", follow_redirects=True, data={
        "payment_method": "credit", "approver": "Owner", "approver_password": "nope"})
    assert "Admin name or password didn&#39;t match" in resp.get_data(as_text=True)
    assert db.session.query(Sale).count() == 0
    admin = db.session.get(User, setup["admin"].id)
    db.session.refresh(admin)
    assert admin.failed_login_attempts == 1


def test_a_cashier_cannot_approve_their_own_over_limit_sale(client, login, setup):
    _over_limit_cart(client, login, setup)
    resp = client.post("/till/checkout", follow_redirects=True, data={
        "payment_method": "credit", "approver": "T1", "approver_password": CASHIER_PASSWORD})
    assert "Only an Admin can approve" in resp.get_data(as_text=True)
    assert db.session.query(Sale).count() == 0


def test_an_admin_at_the_counter_approves_and_both_are_recorded(client, login, setup):
    c = _over_limit_cart(client, login, setup)
    resp = client.post("/till/checkout", follow_redirects=True, data={
        "payment_method": "credit", "approver": "Owner", "approver_password": ADMIN_PASSWORD})
    assert b"Sale complete" in resp.data
    sale = db.session.scalar(db.select(Sale))
    entry = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.sale_id == sale.id))
    assert sale.user_id == setup["cashier"].id
    assert entry.override_authorised_by_user_id == setup["admin"].id
    db.session.expire(c)
    assert c.balance_paisa == 1_020_000


def test_an_archived_khata_cannot_be_chosen(client, login, setup):
    c = _open(setup)
    c.is_active = False
    db.session.commit()
    _as(client, login, "cashier")
    resp = client.post("/till/customer", data={"customer_id": c.id}, follow_redirects=True)
    assert "That Khata could not be found." in resp.get_data(as_text=True)


# --- editing + the error paths ------------------------------------------------------

def test_editing_contact_details(client, login, setup):
    c = _open(setup)
    other = _open(setup, name="Bilal", phone="0321 9874512")
    _as(client, login, "cashier")
    assert client.get(f"/khata/{c.id}/edit").status_code == 200
    resp = client.post(f"/khata/{c.id}/edit", follow_redirects=True, data={
        "name": "Haji Muhammad Usman", "phone": "0300 5541298", "address": "Main Bazaar"})
    assert "Saved." in resp.get_data(as_text=True)
    db.session.expire(c)
    assert (c.name, c.address) == ("Haji Muhammad Usman", "Main Bazaar")

    html = client.post(f"/khata/{c.id}/edit", data={"name": c.name, "phone": other.phone_raw}
                       ).get_data(as_text=True)
    assert "already on Bilal's Khata" in html

    resp = client.post(f"/khata/{c.id}/edit", data={"name": "", "phone": ""})
    assert resp.status_code == 400 and "A name is required." in resp.get_data(as_text=True)


def test_bad_input_is_explained_not_crashed_on(client, login, setup):
    c = _open(setup)
    _as(client, login, "cashier")
    resp = client.post("/khata/new", data={"name": "X", "phone": "12"})
    assert resp.status_code == 400 and "look like a phone number" in resp.get_data(
        as_text=True)
    resp = client.post(f"/khata/{c.id}/payment", data={"amount": "", "method": "cash"})
    assert resp.status_code == 400 and "Enter the amount they paid." in resp.get_data(as_text=True)
    resp = client.post(f"/khata/{c.id}/verify", data={"verify": "telepathy"}, follow_redirects=True)
    assert "Choose how the number was confirmed." in resp.get_data(as_text=True)
    assert client.get("/khata/999/payment").status_code == 404

    _as(client, login, "admin")
    for data, msg in [({"credit_limit": ""}, "Enter a limit in rupees"),
                      ({"credit_limit": "5000", "credit_terms_days": "soon"}, "number of days"),
                      ({"credit_limit": "5000", "credit_terms_days": "0"}, "at least 1 day")]:
        resp = client.post(f"/khata/{c.id}/credit", data=data, follow_redirects=True)
        assert msg in resp.get_data(as_text=True)


def test_a_khata_with_a_balance_cannot_be_archived_from_the_screen(client, login, setup):
    c = _open(setup)
    khata.post_entry(c, entry_type="credit_sale", amount_paisa=50_000, user_id=setup["admin"].id)
    db.session.commit()
    _as(client, login, "admin")
    resp = client.post(f"/khata/{c.id}/remove", follow_redirects=True)
    assert "still owes Rs 500" in resp.get_data(as_text=True)


def test_the_list_filters_and_searches_on_screen(client, login, setup):
    _open(setup)
    _as(client, login, "cashier")
    assert "Haji Usman" in client.get("/khata/?filter=settled").get_data(as_text=True)
    assert "Nobody matches that." in client.get("/khata/?filter=owing").get_data(as_text=True)
    assert "Nobody matches that." in client.get("/khata/?q=zzz").get_data(as_text=True)


def test_initials_skip_symbols(client, login, setup):
    _open(setup, name="Farooq & Sons", phone=None)
    _as(client, login, "cashier")
    html = client.get("/khata/").get_data(as_text=True)
    assert ">FS<" in html and "F&amp;" not in html
