"""Stock movement rules and audit trail (Development Specification Phase 2
Required Tests; edge-case matrix 'Inventory (Phase 2)')."""
from __future__ import annotations

import pytest

from sukoon.extensions import db
from sukoon.models import StockMovement, User
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


@pytest.fixture
def loose(app):
    return inv.create_product(
        name="Loose Atta", sell_price_paisa=17000, allows_fractional=True, unit_label="kg"
    )


def test_stock_in_adds_and_records_before_after(product, user):
    m = inv.apply_stock_movement(
        product=product, movement_type="stock_in", quantity_milli=12000,
        reason="Supplier delivery · PO-8821", user_id=user.id,
    )
    assert (m.quantity_before_milli, m.quantity_delta_milli, m.quantity_after_milli) == (
        0, 12000, 12000,
    )
    assert product.stock_quantity_milli == 12000
    assert m.created_by_user_id == user.id
    assert m.created_at is not None


def test_stock_out_cannot_drive_stock_negative(product, user):
    inv.apply_stock_movement(
        product=product, movement_type="stock_in", quantity_milli=5000,
        reason="in", user_id=user.id,
    )
    with pytest.raises(inv.InsufficientStockError):
        inv.apply_stock_movement(
            product=product, movement_type="stock_out", quantity_milli=6000,
            reason="damage", user_id=user.id,
        )
    assert product.stock_quantity_milli == 5000  # unchanged
    assert db.session.query(StockMovement).count() == 1  # the failed one left nothing


def test_correction_derives_the_delta(product, user):
    inv.apply_stock_movement(
        product=product, movement_type="stock_in", quantity_milli=12000,
        reason="in", user_id=user.id,
    )
    m = inv.apply_stock_movement(
        product=product, movement_type="correction", quantity_milli=8000,
        reason="Physical count", user_id=user.id,
    )
    assert m.quantity_delta_milli == -4000
    assert m.quantity_after_milli == 8000
    assert product.stock_quantity_milli == 8000


def test_every_adjustment_requires_a_reason(product, user):
    with pytest.raises(inv.ValidationError):
        inv.apply_stock_movement(
            product=product, movement_type="stock_in", quantity_milli=1000,
            reason="   ", user_id=user.id,
        )


def test_zero_quantity_is_rejected(product, user):
    with pytest.raises(inv.ValidationError):
        inv.apply_stock_movement(
            product=product, movement_type="stock_in", quantity_milli=0,
            reason="x", user_id=user.id,
        )


def test_loose_product_sells_fractional_and_drops_by_exact_milli(loose, user):
    inv.apply_stock_movement(
        product=loose, movement_type="stock_in", quantity_milli=10000,
        reason="in", user_id=user.id,
    )
    inv.apply_stock_movement(
        product=loose, movement_type="sale", quantity_milli=750,
        reason="sale", user_id=user.id, reference_type="sale", reference_id=1,
    )
    assert loose.stock_quantity_milli == 9250


def test_sealed_pack_cannot_take_a_fractional_quantity(product, user):
    with pytest.raises(inv.FractionalQuantityError):
        inv.apply_stock_movement(
            product=product, movement_type="stock_out", quantity_milli=1500,
            reason="x", user_id=user.id,
        )


def test_refund_movement_adds_stock_back(product, user):
    inv.apply_stock_movement(
        product=product, movement_type="stock_in", quantity_milli=5000,
        reason="in", user_id=user.id,
    )
    inv.apply_stock_movement(
        product=product, movement_type="refund", quantity_milli=1000,
        reason="return", user_id=user.id,
    )
    assert product.stock_quantity_milli == 6000
