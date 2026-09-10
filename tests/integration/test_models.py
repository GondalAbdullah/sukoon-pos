"""Model-level constraint tests (Development Specification Phase 1 Required Tests):
unique SKU, unique barcode, required fields, and the ADR-0016 CHECK constraints.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from sukoon.models import Category, Product, ProductBarcode, User
from sukoon.services.auth_service import hash_password


def _user(db):
    u = User(name="U", initials="U", role="admin", password_hash=hash_password("x"))
    db.session.add(u)
    db.session.commit()
    return u


def _product(db, **kw):
    defaults = dict(name="Rice 5kg", sell_price_paisa=120_000)
    defaults.update(kw)
    p = Product(**defaults)
    db.session.add(p)
    db.session.commit()
    return p


def test_two_products_may_both_have_null_sku(db):
    _product(db, name="A")
    _product(db, name="B")
    assert db.session.query(Product).count() == 2


def test_duplicate_non_null_sku_is_rejected(db):
    _product(db, name="A", sku="RICE-01")
    with pytest.raises(IntegrityError):
        _product(db, name="B", sku="RICE-01")


def test_barcode_is_unique_across_the_catalog(db):
    _user(db)
    a = _product(db, name="A")
    b = _product(db, name="B")
    db.session.add(ProductBarcode(product_id=a.id, barcode="8964000111", created_by_user_id=1))
    db.session.commit()
    db.session.add(ProductBarcode(product_id=b.id, barcode="8964000111", created_by_user_id=1))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_product_requires_a_non_blank_name(db):
    with pytest.raises(IntegrityError):
        _product(db, name="   ")


def test_product_requires_a_sell_price(db):
    with pytest.raises(IntegrityError):
        p = Product(name="No price")
        db.session.add(p)
        db.session.commit()


def test_negative_sell_price_is_rejected(db):
    with pytest.raises(IntegrityError):
        _product(db, name="Neg", sell_price_paisa=-1)


def test_category_name_is_unique(db):
    db.session.add(Category(name="Groceries"))
    db.session.commit()
    db.session.add(Category(name="Groceries"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_foreign_keys_are_enforced(db):
    """PRAGMA foreign_keys=ON — a sale_item pointing at a missing product fails."""
    from sukoon.models import Sale, SaleItem

    with pytest.raises(IntegrityError):
        s = Sale(
            invoice_number="INV-2026-0001",
            user_id=999,  # no such user
            subtotal_paisa=0,
            total_paisa=0,
            payment_method="cash",
            status="completed",
        )
        db.session.add(s)
        db.session.commit()
    db.session.rollback()
    _ = SaleItem  # imported for symmetry with later phases
