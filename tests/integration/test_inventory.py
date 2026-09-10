"""Category/product CRUD, SKU generation, provisional state, delete, search,
low-stock alerting (Development Specification Phase 2, ADR-0011/0012/0018)."""
from __future__ import annotations

import re

import pytest

from sukoon.extensions import db
from sukoon.models import Product, User
from sukoon.services import inventory_service as inv
from sukoon.services.auth_service import hash_password


@pytest.fixture
def user(app):
    u = User(name="Admin", initials="AD", role="admin", password_hash=hash_password("x"))
    db.session.add(u)
    db.session.commit()
    return u


def _mk(**kw):
    d = dict(name="Thing", sell_price_paisa=10000)
    d.update(kw)
    return inv.create_product(**d)


# --- SKU (ADR-0018) ---

def test_created_product_gets_a_category_derived_sku(app):
    cat = inv.create_category("Cooking Oils & Ghee")
    p = _mk(name="Dalda", category=cat)
    assert re.match(r"^[A-Z]{2,3}-\d{4,}$", p.sku)
    assert p.sku.startswith("COO-")


def test_product_without_category_gets_gen_sku(app):
    assert _mk().sku.startswith("GEN-")


def test_same_prefix_still_unique_skus(app):
    c1 = inv.create_category("Grains")
    c2 = inv.create_category("Grocery Bulk")  # both -> "GRA"/"GRO"? force clash
    c3 = inv.create_category("Granola Bars")
    a = _mk(name="a", category=c1)
    b = _mk(name="b", category=c3)
    assert a.sku != b.sku
    assert c2  # silence lint


def test_changing_category_does_not_change_sku(app):
    c1 = inv.create_category("Oils")
    c2 = inv.create_category("Dairy")
    p = _mk(category=c1)
    original = p.sku
    inv.update_product(p, category_id=c2.id)
    assert p.sku == original


def test_editing_sku_to_an_existing_value_is_rejected(app):
    a = _mk(name="a")
    b = _mk(name="b")
    with pytest.raises(inv.DuplicateSkuError):
        inv.update_product(b, sku=a.sku)


# --- provisional (ADR-0011/0012) ---

def test_product_missing_tier_c_is_provisional(app):
    p = _mk()  # no cost, category, threshold
    assert p.is_provisional is True


def test_completing_a_provisional_product_clears_the_flag(app):
    cat = inv.create_category("X")
    p = _mk()
    assert p.is_provisional
    inv.update_product(
        p, cost_price_paisa=8000, category_id=cat.id, low_stock_threshold_milli=5000
    )
    assert p.is_provisional is False


def test_barcodeless_product_is_not_provisional(app):
    cat = inv.create_category("X")
    p = _mk(cost_price_paisa=8000, category=cat, low_stock_threshold_milli=1000)
    assert p.is_provisional is False  # no barcode, still complete (ADR-0012)


def test_provisional_products_appear_in_needs_completing_filter(app):
    inv.create_category("X")
    _mk(name="incomplete")
    cat = inv.create_category("Y")
    _mk(name="complete", cost_price_paisa=100, category=cat, low_stock_threshold_milli=1)
    rows, total = inv.list_products(needs_completing=True)
    assert [r.name for r in rows] == ["incomplete"]
    assert total == 1


# --- validation ---

def test_product_needs_a_name_and_whole_rupee_price(app):
    with pytest.raises(inv.ValidationError):
        _mk(name="  ")
    with pytest.raises(inv.ValidationError):
        _mk(sell_price_paisa=10050)  # not a whole rupee


# --- delete (edge case) ---

def test_delete_without_history_is_a_hard_delete(app):
    p = _mk()
    pid = p.id
    assert inv.delete_product(p) == "hard"
    assert db.session.get(Product, pid) is None


def test_delete_with_movement_history_is_a_soft_delete(app, user):
    p = _mk()
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=5000,
        reason="initial", user_id=user.id,
    )
    pid = p.id
    assert inv.delete_product(p) == "soft"
    row = db.session.get(Product, pid)
    assert row is not None and row.is_active is False


# --- search ---

def test_search_matches_name_sku_and_barcode(app, user):
    cat = inv.create_category("Beverages")
    p = _mk(name="Tapal Danedar Tea", category=cat)
    inv.assign_barcode(product=p, code="8964000111222", user_id=user.id)
    assert inv.list_products(query="danedar")[1] == 1
    assert inv.list_products(query=p.sku)[1] == 1
    assert inv.list_products(query="8964000111222")[1] == 1
    assert inv.list_products(query="nonsense")[1] == 0


# --- low stock (Phase 2 required test: fires exactly at the boundary) ---

def test_low_stock_list_fires_exactly_at_threshold(app, user):
    p = _mk(low_stock_threshold_milli=10000)
    inv.apply_stock_movement(
        product=p, movement_type="stock_in", quantity_milli=11000,
        reason="in", user_id=user.id,
    )
    assert p not in inv.low_stock_products()  # 11 > 10
    inv.apply_stock_movement(
        product=p, movement_type="stock_out", quantity_milli=1000,
        reason="out", user_id=user.id,
    )
    assert p in inv.low_stock_products()  # exactly 10


def test_catalog_summary_counts(app, user):
    cat = inv.create_category("C")
    a = _mk(name="a", cost_price_paisa=10000, category=cat, low_stock_threshold_milli=2000)
    inv.apply_stock_movement(
        product=a, movement_type="stock_in", quantity_milli=3000,
        reason="in", user_id=user.id,
    )
    _mk(name="b")  # out of stock, provisional
    s = inv.catalog_summary()
    assert s["catalog_size"] == 2
    assert s["out_of_stock"] == 1
    assert s["stock_value_paisa"] == 30000  # 10000 paisa * 3 units
