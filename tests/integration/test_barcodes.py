"""Barcode assignment, generation, and the resolver chain (ADR-0009, ADR-0018;
edge-case matrix 'Barcodes and relabelling (Phase 2)')."""
from __future__ import annotations

import re

import pytest
from sqlalchemy.exc import IntegrityError

from sukoon.extensions import db
from sukoon.models import ProductBarcode, User
from sukoon.services import inventory_service as inv
from sukoon.services.auth_service import hash_password


@pytest.fixture
def user(app):
    u = User(name="U", initials="U", role="admin", password_hash=hash_password("x"))
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def product(app):
    return inv.create_product(name="Dalda 5L", sell_price_paisa=285000)


def test_generated_barcode_has_sk_prefix_and_resolves(product, user):
    row = inv.generate_barcode(product=product, user_id=user.id)
    assert re.match(r"^SK-\d{6}$", row.barcode)
    match = inv.resolve_barcode(row.barcode)
    assert match.product.id == product.id
    assert match.unit_price_paisa == 285000  # no override -> product price


def test_two_barcodes_resolve_to_one_product_at_their_own_prices(product, user):
    inv.assign_barcode(product=product, code="8964000109283", user_id=user.id)
    inv.assign_barcode(
        product=product, code="CLEAR-01", user_id=user.id, price_override_paisa=200000,
        label="Near expiry",
    )
    assert inv.resolve_barcode("8964000109283").unit_price_paisa == 285000
    assert inv.resolve_barcode("CLEAR-01").unit_price_paisa == 200000
    # a product's normal price is unaffected by an override barcode existing
    assert product.sell_price_paisa == 285000


def test_duplicate_barcode_is_rejected_by_the_service(product, user):
    other = inv.create_product(name="Other", sell_price_paisa=1000)
    inv.assign_barcode(product=product, code="DUP-1", user_id=user.id)
    with pytest.raises(inv.DuplicateBarcodeError):
        inv.assign_barcode(product=other, code="DUP-1", user_id=user.id)


def test_duplicate_barcode_is_rejected_at_the_database_level(product, user):
    inv.assign_barcode(product=product, code="DB-DUP", user_id=user.id)
    db.session.add(
        ProductBarcode(product_id=product.id, barcode="DB-DUP", created_by_user_id=user.id)
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deactivating_a_barcode_stops_it_resolving(product, user):
    row = inv.assign_barcode(product=product, code="PROMO-9", user_id=user.id)
    assert inv.resolve_barcode("PROMO-9") is not None
    inv.deactivate_barcode(row)
    assert inv.resolve_barcode("PROMO-9") is None


def test_unknown_code_returns_none_not_an_exception(app):
    assert inv.resolve_barcode("nope") is None
    assert inv.resolve_barcode("") is None


def test_generated_and_manufacturer_codes_use_one_chain(product, user):
    gen = inv.generate_barcode(product=product, user_id=user.id)
    inv.assign_barcode(product=product, code="8964000109283", user_id=user.id)
    assert inv.resolve_barcode(gen.barcode).product.id == product.id
    assert inv.resolve_barcode("8964000109283").product.id == product.id
