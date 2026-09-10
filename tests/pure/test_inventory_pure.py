"""Pure unit tests for inventory_service — no database, no app context."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sukoon.services import inventory_service as inv


def _p(**kw):
    base = dict(
        cost_price_paisa=1000,
        category_id=1,
        low_stock_threshold_milli=5000,
        stock_quantity_milli=10000,
        low_stock_threshold=None,
        unit_label="unit",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- SKU prefix (ADR-0018) ---

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Cooking Oils & Ghee", "COO"),
        ("Grains & Flours", "GRA"),
        ("Tea", "TEA"),
        ("A1 Sauces", "ASA"),  # digits + space stripped, then first 3 letters
    ],
)
def test_category_prefix(name, expected):
    assert inv.compute_category_prefix(SimpleNamespace(name=name)) == expected


def test_category_prefix_none_is_gen():
    assert inv.compute_category_prefix(None) == "GEN"


def test_category_prefix_all_symbols_falls_back_to_gen():
    assert inv.compute_category_prefix(SimpleNamespace(name="123 / 456")) == "GEN"


# --- provisional (ADR-0011/0012) ---

def test_provisional_when_any_tier_c_field_missing():
    assert inv.compute_is_provisional(_p(cost_price_paisa=None)) is True
    assert inv.compute_is_provisional(_p(category_id=None)) is True
    assert inv.compute_is_provisional(_p(low_stock_threshold_milli=None)) is True


def test_not_provisional_when_all_tier_c_present():
    assert inv.compute_is_provisional(_p()) is False


# --- stock status boundary (Phase 2 required test) ---

def test_stock_status_boundary():
    assert inv.compute_stock_status(_p(stock_quantity_milli=5001)) == "healthy"
    assert inv.compute_stock_status(_p(stock_quantity_milli=5000)) == "low"  # exactly at
    assert inv.compute_stock_status(_p(stock_quantity_milli=1)) == "low"
    assert inv.compute_stock_status(_p(stock_quantity_milli=0)) == "out"


def test_stock_status_null_threshold_never_low():
    assert inv.compute_stock_status(
        _p(low_stock_threshold_milli=None, stock_quantity_milli=1)
    ) == "healthy"


# --- money / quantity validation (ADR-0007 / ADR-0004) ---

def test_whole_rupee_validation():
    assert inv.validate_whole_rupee(15000, field="x") == 15000
    with pytest.raises(inv.ValidationError):
        inv.validate_whole_rupee(15050, field="x")  # not a whole rupee
    with pytest.raises(inv.ValidationError):
        inv.validate_whole_rupee(-100, field="x")
    with pytest.raises(inv.ValidationError):
        inv.validate_whole_rupee(None, field="x")


def test_fractional_quantity_rejected_for_sealed_pack():
    with pytest.raises(inv.FractionalQuantityError):
        inv.validate_quantity_milli(1500, allows_fractional=False)
    assert inv.validate_quantity_milli(2000, allows_fractional=False) == 2000
    assert inv.validate_quantity_milli(1500, allows_fractional=True) == 1500
