"""Khata — customers, ledger, payments, limits (Development Specification Phase 4;
ADR-0013, ADR-0014, ADR-0015, ADR-0026)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Customer, Payment, Sale
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import ledger, refund_service, sales_service, settings_service
from sukoon.services.refund_service import RefundLineSpec
from sukoon.services.sales_service import CartLine

JAN = datetime(2026, 1, 10, tzinfo=UTC)


@pytest.fixture
def staff(seeded):
    seed_invoice_counter()
    return seeded


@pytest.fixture
def ghee(staff):
    p = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=500_000,
                             reason="in", user_id=staff["admin"].id)
    return p


def _open(staff, name="Haji Usman", phone="0300 5541298", **kw):
    return khata.create_customer(name=name, phone_raw=phone, user_id=staff["cashier"].id, **kw)


def _credit_sale(staff, customer, product, units, **kw):
    return sales_service.record_sale(
        lines=[CartLine(product=product, quantity_milli=units * 1000,
                        unit_price_paisa=product.sell_price_paisa, quantity_source="stepper")],
        payment_method="credit", customer_id=customer.id,
        user_id=staff["cashier"].id, now=JAN, **kw)


def _assert_reconciles(customer):
    db.session.expire(customer)
    cached, from_ledger = khata.reconcile(customer)
    assert cached == from_ledger


# --- opening a Khata (ADR-0013, ADR-0026 §2) ----------------------------------

def test_a_new_khata_gets_the_shop_default_limit(staff):
    assert _open(staff).credit_limit_paisa == 1_000_000  # Rs 10,000, client's choice
    settings_service.set("khata.default_credit_limit_paisa", 2_500_000)
    db.session.commit()
    assert _open(staff, name="B", phone=None).credit_limit_paisa == 2_500_000


def test_a_duplicate_number_asks_first_then_is_allowed(staff):
    _open(staff, phone="0300 5541298")
    with pytest.raises(khata.DuplicatePhoneError, match="Haji Usman's Khata. Same person?"):
        _open(staff, name="Usman Traders", phone="+92 300 5541298")  # another spelling
    second = _open(staff, name="Usman Traders", phone="+92 300 5541298", confirm_duplicate=True)
    assert second.phone_normalised == "+923005541298" and second.phone_raw == "+92 300 5541298"


def test_an_unreadable_number_is_refused_not_guessed(staff):
    with pytest.raises(khata.CustomerValidationError) as err:
        _open(staff, phone="0300 55412")
    assert err.value.field == "phone"


def test_a_customer_with_no_phone_can_hold_a_khata_and_buy(staff, ghee):
    c = _open(staff, name="Walk-up Regular", phone="")
    assert c.phone_normalised is None
    _credit_sale(staff, c, ghee, 1)
    assert c.balance_paisa == 60_000


def test_verification_records_who_when_and_how(staff):
    c = _open(staff, verified_method="shown")
    assert c.phone_verified and c.phone_verified_method == "shown"
    assert c.phone_verified_by_user_id == staff["cashier"].id and c.phone_verified_at


def test_changing_a_verified_number_clears_its_verification(staff):
    c = _open(staff, verified_method="called")
    khata.update_contact(c, name=c.name, phone_raw="0321 9874512", address=None, notes=None)
    assert not c.phone_verified and c.phone_verified_method is None


# --- ledger + payments (Phase 4 steps 2–3; required tests) ----------------------

def test_ledger_balance_is_correct_across_mixed_sales_and_payments(staff, ghee):
    # the Development Spec's DoD: "reconciles to zero across a full scripted scenario"
    c = _open(staff)
    khata.set_credit_terms(c, credit_limit_paisa=None, credit_terms_days=30)
    steps = [
        ("sale", 3, 180_000), ("pay", 50_000, 130_000), ("sale", 2, 250_000),
        ("pay", 100_000, 150_000), ("sale", 1, 210_000), ("pay", 210_000, 0),
    ]
    for kind, n, expected in steps:
        if kind == "sale":
            _credit_sale(staff, c, ghee, n)
        else:
            khata.record_payment(customer_id=c.id, amount_paisa=n, method="cash",
                                 received_by_user_id=staff["cashier"].id)
        _assert_reconciles(c)
        assert c.balance_paisa == expected
    assert c.balance_paisa == 0
    entries = khata.entries_for(c.id)
    assert [e.entry_type for e in entries] == ["credit_sale", "payment"] * 3
    assert all(e.balance_after_paisa == s[2] for e, s in zip(entries, steps, strict=True))


def test_a_payment_writes_the_payment_its_entry_and_the_balance_together(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 1)
    p = khata.record_payment(customer_id=c.id, amount_paisa=20_000, method="mobile_wallet",
                             reference="TX-88213", received_by_user_id=staff["cashier"].id)
    entry = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.payment_id == p.id))
    assert entry.amount_paisa == -20_000 and entry.balance_after_paisa == 40_000
    assert "JazzCash / Easypaisa · TX-88213" == entry.note
    assert p.received_by_user_id == staff["cashier"].id


def test_a_failed_payment_leaves_nothing_behind(staff, ghee, monkeypatch):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 1)

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(khata, "post_entry", boom)
    with pytest.raises(RuntimeError):
        khata.record_payment(customer_id=c.id, amount_paisa=10_000, method="cash",
                             received_by_user_id=staff["cashier"].id)
    assert db.session.query(Payment).count() == 0
    db.session.expire(c)
    assert c.balance_paisa == 60_000


@pytest.mark.parametrize("amount,field", [(None, "amount"), (0, "amount"), (-100, "amount"),
                                          (10_050, "amount")])
def test_a_payment_needs_a_whole_positive_amount(staff, amount, field):
    c = _open(staff)
    with pytest.raises(khata.CustomerValidationError) as err:
        khata.record_payment(customer_id=c.id, amount_paisa=amount, method="cash",
                             received_by_user_id=staff["cashier"].id)
    assert err.value.field == field


def test_overpayment_is_explicit_credit_not_a_silent_negative(staff, ghee):
    # required test: "an explicit credit-balance state, not a silent or confusing negative"
    c = _open(staff)
    _credit_sale(staff, c, ghee, 1)  # owes Rs 600
    with pytest.raises(khata.OverpaymentError) as err:
        khata.record_payment(customer_id=c.id, amount_paisa=80_000, method="cash",
                             received_by_user_id=staff["cashier"].id)
    assert err.value.excess_paisa == 20_000
    assert db.session.query(Payment).count() == 0  # nothing happened until confirmed

    khata.record_payment(customer_id=c.id, amount_paisa=80_000, method="cash",
                         received_by_user_id=staff["cashier"].id, allow_overpayment=True)
    state = ledger.describe_balance(c.balance_paisa)
    assert (state.kind, state.amount_paisa) == ("in_credit", 20_000)

    _credit_sale(staff, c, ghee, 1)  # the credit is used by the next purchase
    assert c.balance_paisa == 40_000
    _assert_reconciles(c)


def test_a_credit_refund_goes_through_the_same_ledger_writer(staff, ghee):
    c = _open(staff)
    sale = _credit_sale(staff, c, ghee, 2)
    r = refund_service.initiate_refund(
        sale_id=sale.id, lines=[RefundLineSpec(sale_item_id=sale.items[0].id, quantity_milli=1000)],
        reason="wrong size", initiated_by_user_id=staff["cashier"].id)
    refund_service.approve_refund(refund_id=r.id, approved_by_user_id=staff["admin"].id)
    assert c.balance_paisa == 60_000
    _assert_reconciles(c)


# --- deleting (required test; ADR-0026 §8) -------------------------------------

def test_a_customer_who_owes_cannot_be_removed(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 1)
    with pytest.raises(khata.CustomerHasBalanceError, match="still owes Rs 600"):
        khata.remove_customer(c)
    assert db.session.get(Customer, c.id).is_active


def test_a_customer_in_credit_cannot_be_removed_either(staff):
    c = _open(staff)
    khata.record_payment(customer_id=c.id, amount_paisa=5_000, method="cash",
                         received_by_user_id=staff["cashier"].id, allow_overpayment=True)
    with pytest.raises(khata.CustomerHasBalanceError, match="in credit"):
        khata.remove_customer(c)


def test_a_settled_customer_with_history_is_archived_not_deleted(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 1)
    khata.record_payment(customer_id=c.id, amount_paisa=60_000, method="cash",
                         received_by_user_id=staff["cashier"].id)
    assert khata.remove_customer(c) == "archived"
    assert db.session.get(Customer, c.id).is_active is False
    assert db.session.query(Sale).count() == 1  # history intact
    rows, counts = khata.list_customers()
    assert rows == [] and counts["all"] == 0
    with pytest.raises(sales_service.PaymentError):  # and it can't be sold to
        _credit_sale(staff, c, ghee, 1)


def test_a_customer_with_no_history_is_deleted_outright(staff):
    c = _open(staff)
    assert khata.remove_customer(c) == "deleted"
    assert db.session.get(Customer, c.id) is None


# --- credit limit (ADR-0014) -----------------------------------------------------

def test_a_sale_within_the_limit_succeeds_for_a_cashier(staff, ghee):
    c = _open(staff)  # Rs 10,000
    _credit_sale(staff, c, ghee, 16)  # Rs 9,600
    assert c.balance_paisa == 960_000


def test_a_sale_past_the_limit_is_blocked_and_nothing_is_written(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 16)  # Rs 9,600
    with pytest.raises(khata.CreditLimitExceededError) as err:
        _credit_sale(staff, c, ghee, 1)  # -> Rs 10,200
    assert err.value.over_by_paisa == 20_000
    assert db.session.query(Sale).count() == 1
    db.session.expire(ghee)
    assert ghee.stock_quantity_milli == 484_000  # no stock left the shelf either


def test_an_admin_override_records_both_people(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 16)
    sale = _credit_sale(staff, c, ghee, 1, override_authorised_by_user_id=staff["admin"].id)
    entry = db.session.scalar(
        db.select(CreditLedgerEntry).where(CreditLedgerEntry.sale_id == sale.id))
    assert entry.override_authorised_by_user_id == staff["admin"].id
    assert sale.user_id == staff["cashier"].id  # the cashier who rang it, distinct
    assert entry.note == "Over-limit, approved by Owner"


def test_a_cashier_cannot_be_named_as_the_approver(staff, ghee):
    c = _open(staff)
    _credit_sale(staff, c, ghee, 16)
    with pytest.raises(khata.KhataError, match="Only an Admin"):
        _credit_sale(staff, c, ghee, 1, override_authorised_by_user_id=staff["cashier"].id)


def test_a_null_limit_is_never_blocked(staff, ghee):
    c = _open(staff)
    khata.set_credit_terms(c, credit_limit_paisa=None, credit_terms_days=None)
    _credit_sale(staff, c, ghee, 400)
    assert c.balance_paisa == 24_000_000


def test_a_limit_must_be_whole_non_negative_rupees(staff):
    c = _open(staff)
    for bad in (-100, 10_050):
        with pytest.raises(khata.CustomerValidationError):
            khata.set_credit_terms(c, credit_limit_paisa=bad, credit_terms_days=None)


# --- the list -----------------------------------------------------------------

def test_the_list_counts_and_filters_by_balance_state(staff, ghee):
    owes = _open(staff, name="Owes", phone=None)
    _credit_sale(staff, owes, ghee, 1)
    _open(staff, name="Settled", phone=None)
    credit = _open(staff, name="Credit", phone=None)
    khata.record_payment(customer_id=credit.id, amount_paisa=1_000, method="cash",
                         received_by_user_id=staff["cashier"].id, allow_overpayment=True)
    rows, counts = khata.list_customers(filter_="owing")
    assert [r.customer.name for r in rows] == ["Owes"]
    assert counts == {"all": 3, "owing": 1, "settled": 1, "in_credit": 1}
    rows, _ = khata.list_customers(query="5541298")  # search by number fragment
    assert rows == []
    _open(staff, name="Phone Match", phone="0300 5541298")
    rows, _ = khata.list_customers(query="+92 300 5541298")
    assert [r.customer.name for r in rows] == ["Phone Match"]
