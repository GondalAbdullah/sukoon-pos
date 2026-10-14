"""One person, several Khatas on one phone number — home, office, a brother's
(ADR-0042). Labels, the name+label rule, carried-over confirmation, per-Khata limits,
the screens, and WhatsApp messages that say which Khata they are about."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from sukoon.extensions import db
from sukoon.models import Customer, NotificationQueue
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import sales_service, settings_service
from sukoon.services.notifications import queue
from sukoon.services.notifications.providers.base import FakeProvider
from sukoon.services.sales_service import CartLine
from tests.conftest import CASHIER_PASSWORD

ALI = "0300 5541298"
NOW = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)


@pytest.fixture
def staff(seeded):
    seed_invoice_counter()
    return seeded


def _open(staff, label=None, *, name="Ali Raza", phone=ALI, **kw):
    kw.setdefault("confirm_duplicate", True)
    return khata.create_customer(name=name, label=label, phone_raw=phone,
                                 user_id=staff["cashier"].id, **kw)


# --- labels and the name + label rule (§1, §2) ------------------------------------

def test_a_khata_is_named_with_its_label_or_just_its_name(staff):
    assert _open(staff, "Home").display_name == "Ali Raza (Home)"
    assert _open(staff, name="Bilal", phone=None).display_name == "Bilal"


def test_a_blank_label_is_no_label_and_spaces_are_tidied(staff):
    assert _open(staff, "   ").label is None
    assert _open(staff, "  Office   upstairs ").label == "Office upstairs"


def test_a_label_over_40_characters_is_refused(staff):
    with pytest.raises(khata.CustomerValidationError) as exc:
        _open(staff, "x" * 41)
    assert exc.value.field == "label"


def test_ali_opens_home_office_and_his_brothers_khata_on_one_number(staff):
    home, office = _open(staff, "Home"), _open(staff, "Office")
    brother = _open(staff, "Brother – Bilal")
    assert {c.phone_normalised for c in (home, office, brother)} == {"+923005541298"}
    assert len({home.id, office.id, brother.id}) == 3


def test_the_same_name_and_label_twice_on_one_number_is_refused(staff):
    _open(staff, "Home")
    with pytest.raises(khata.CustomerValidationError, match="Give this one a label") as exc:
        _open(staff, " home ")  # case and spaces don't make it different
    assert exc.value.field == "label"
    _open(staff)  # no label is itself distinct from "Home"
    with pytest.raises(khata.CustomerValidationError):
        _open(staff, name="ali raza")


def test_the_same_name_is_fine_on_different_numbers_or_with_no_number(staff):
    _open(staff, "Home")
    _open(staff, "Home", phone="0321 9874512")
    _open(staff, "Home", phone=None)
    _open(staff, "Home", phone=None)
    assert db.session.query(Customer).count() == 4


def test_an_archived_khata_does_not_block_the_name(staff):
    old = _open(staff, "Home")
    khata.remove_customer(old)  # no history: deleted outright
    _open(staff, "Home")


def test_the_duplicate_question_still_comes_first(staff):
    _open(staff, "Home")
    with pytest.raises(khata.DuplicatePhoneError,
                       match=r"already has a Khata: Ali Raza \(Home\)\. Open another"):
        _open(staff, "Office", confirm_duplicate=False)


def test_editing_into_a_clash_is_refused_but_unrelated_edits_are_not(staff):
    _open(staff, "Home")
    office = _open(staff, "Office")
    with pytest.raises(khata.CustomerValidationError):
        khata.update_contact(office, name="Ali Raza", label="HOME", phone_raw=ALI,
                             address=None, notes=None)
    db.session.rollback()
    khata.update_contact(office, name="Ali Raza", label="Office", phone_raw=ALI,
                         address="Blue Area", notes=None)
    assert office.address == "Blue Area"


def test_two_unlabelled_khatas_from_before_can_still_have_their_notes_edited(staff):
    """Data from before ADR-0042 may already hold two identical names on one number."""
    a = _open(staff)
    b = Customer(name="Ali Raza", phone_raw=ALI, phone_normalised=a.phone_normalised,
                 balance_paisa=0)
    db.session.add(b)
    db.session.commit()
    khata.update_contact(b, name="Ali Raza", label=None, phone_raw=ALI, address=None,
                         notes="pays on Fridays")
    assert b.notes == "pays on Fridays"
    khata.update_contact(b, name="Ali Raza", label="Office", phone_raw=ALI, address=None,
                         notes=None)
    assert b.display_name == "Ali Raza (Office)"


# --- limits stay per Khata (§4) -----------------------------------------------------

def test_each_khata_gets_the_default_limit_on_its_own(staff):
    settings_service.set("khata.default_credit_limit_paisa", 500_000)
    db.session.commit()
    home, office = _open(staff, "Home"), _open(staff, "Office")
    assert (home.credit_limit_paisa, office.credit_limit_paisa) == (500_000, 500_000)
    khata.set_credit_terms(home, credit_limit_paisa=100_000, credit_terms_days=None)
    db.session.refresh(office)
    assert office.credit_limit_paisa == 500_000


# --- confirmation carries over, recorded (§5) --------------------------------------

def test_a_number_confirmed_on_another_khata_carries_over(staff):
    home = _open(staff, "Home", verified_method="shown")
    office = _open(staff, "Office")
    assert office.phone_verified and office.phone_verified_method == "same_number"
    assert office.phone_verified_from_customer_id == home.id
    assert office.phone_verified_by_user_id == staff["cashier"].id
    assert office.phone_verified_at is not None


def test_the_cashiers_own_confirmation_wins(staff):
    _open(staff, "Home", verified_method="shown")
    office = _open(staff, "Office", verified_method="called")
    assert (office.phone_verified_method, office.phone_verified_from_customer_id) == (
        "called", None)


def test_an_unconfirmed_number_carries_nothing(staff):
    _open(staff, "Home")
    assert not _open(staff, "Office").phone_verified


def test_an_archived_khatas_confirmation_does_not_carry(staff):
    home = _open(staff, "Home", verified_method="shown")
    home.is_active = False
    db.session.commit()
    assert not _open(staff, "Office").phone_verified


def test_whatsapp_agreement_is_never_carried_over(staff):
    _open(staff, "Home", verified_method="shown", whatsapp_opt_in=True)
    assert not _open(staff, "Office").whatsapp_opt_in


def test_editing_onto_a_confirmed_number_carries_it_too(staff):
    home = _open(staff, "Home", verified_method="shown")
    bilal = _open(staff, name="Bilal", phone="0321 9874512")
    khata.update_contact(bilal, name="Bilal", label=None, phone_raw=ALI, address=None,
                         notes=None, confirm_duplicate=True, user_id=staff["admin"].id)
    assert bilal.phone_verified_method == "same_number"
    assert bilal.phone_verified_from_customer_id == home.id
    assert bilal.phone_verified_by_user_id == staff["admin"].id


def test_confirming_in_person_later_replaces_the_carried_over_record(staff):
    _open(staff, "Home", verified_method="shown")
    office = _open(staff, "Office")
    khata.verify_phone(office, method="called", user_id=staff["admin"].id)
    assert (office.phone_verified_method, office.phone_verified_from_customer_id) == (
        "called", None)


# --- search -------------------------------------------------------------------------

def test_the_till_finds_a_khata_by_its_label(staff):
    _open(staff, "Home")
    office = _open(staff, "Office")
    assert [c.id for c in khata.search_for_till("offi")] == [office.id]
    assert len(khata.search_for_till("Ali")) == 2


# --- screens ------------------------------------------------------------------------

def _cashier(client, login):
    client.post("/logout")
    login("T1", CASHIER_PASSWORD)


def test_the_form_opens_another_khata_on_a_known_number(client, login, staff):
    _open(staff, "Home", verified_method="shown")
    _cashier(client, login)
    form = client.get("/khata/new").get_data(as_text=True)
    assert 'name="label"' in form
    html = client.post("/khata/new", data={"name": "Ali Raza", "label": "Office",
                                           "phone": ALI}).get_data(as_text=True)
    assert "This number already has a Khata: Ali Raza (Home). Open another Khata on it?" in html
    assert "already confirmed on Ali Raza (Home), so this Khata will be too" in html
    assert "Open another Khata on this number" in html
    assert "use the existing Khata instead" not in html
    resp = client.post("/khata/new", follow_redirects=True, data={
        "name": "Ali Raza", "label": "Office", "phone": ALI, "confirm_duplicate": "1"})
    page = resp.get_data(as_text=True)
    assert "Khata opened for Ali Raza (Office)." in page
    assert "already confirmed on Ali Raza (Home)" in page


def test_the_form_refuses_a_second_unlabelled_khata(client, login, staff):
    _open(staff)
    _cashier(client, login)
    resp = client.post("/khata/new", data={"name": "Ali Raza", "phone": ALI,
                                           "confirm_duplicate": "1"})
    assert resp.status_code == 400
    assert "Give this one a label" in resp.get_data(as_text=True)
    assert db.session.query(Customer).count() == 1


def test_the_till_picker_shows_the_label(client, login, staff):
    _open(staff, "Home")
    _open(staff, "Office")
    _cashier(client, login)
    html = client.get("/till/customers?q=Ali").get_data(as_text=True)
    assert "Ali Raza (Home)" in html and "Ali Raza (Office)" in html


def test_editing_sets_a_label(client, login, staff):
    c = _open(staff)
    _cashier(client, login)
    client.post(f"/khata/{c.id}/edit", data={"name": "Ali Raza", "label": "Home",
                                              "phone": ALI})
    db.session.expire(c)
    assert c.display_name == "Ali Raza (Home)"


# --- WhatsApp names the Khata (§7) ---------------------------------------------------

def _enable():
    settings_service.set(queue.REPLY_TO, "0300 1234567")
    db.session.commit()
    queue.set_enabled(True, key_present=True)


def _credit_sale(staff, c, product):
    return sales_service.record_sale(
        lines=[CartLine(product=product, quantity_milli=1000,
                        unit_price_paisa=product.sell_price_paisa, quantity_source="stepper")],
        payment_method="credit", customer_id=c.id, user_id=staff["cashier"].id)


def test_ali_can_tell_his_khatas_apart_on_whatsapp(staff):
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=ghee, movement_type="stock_in", quantity_milli=10_000,
                             reason="in", user_id=staff["admin"].id)
    _enable()
    home = _open(staff, "Home", verified_method="shown", whatsapp_opt_in=True)
    office = _open(staff, "Office", whatsapp_opt_in=True)  # confirmation carried over
    _credit_sale(staff, home, ghee)
    _credit_sale(staff, office, ghee)
    for row in db.session.scalars(db.select(NotificationQueue)):
        row.created_at = NOW
    db.session.commit()

    provider = FakeProvider()
    assert queue.process_due(provider, now=NOW).sent == 2
    texts = sorted(m.text for m in provider.sent)
    assert {m.to for m in provider.sent} == {"+923005541298"}
    assert "added to the Khata of Ali Raza (Home) as of" in texts[0]
    assert "added to the Khata of Ali Raza (Office) as of" in texts[1]


def test_a_message_queued_before_the_khata_was_named_is_filled_at_send_time(staff):
    _enable()
    c = _open(staff, "Home", verified_method="shown", whatsapp_opt_in=True)
    db.session.add(NotificationQueue(
        customer_id=c.id, notification_type="payment_receipt", dedupe_key="payment:old",
        payload_json=json.dumps({"amount": "Rs 500", "as_of": "14 Sep 2026, 8:26 PM",
                                 "new": "Settled"}),
        status="pending", attempt_count=0, created_at=NOW))
    db.session.commit()
    provider = FakeProvider()
    assert queue.process_due(provider, now=NOW).sent == 1
    assert "received on the Khata of Ali Raza (Home) as of" in provider.sent[0].text
