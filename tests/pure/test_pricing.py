"""Pure tests for cart/line arithmetic (ADR-0004, ADR-0005, ADR-0007).

Covers the edge-case matrix under 'Weighed-item entry (Phase 3)' and
'Money and rounding (Phase 3)'.
"""
from __future__ import annotations

import pytest

from sukoon.services import pricing
from sukoon.services.money import is_whole_rupee

# --- by weight -> line total (ADR-0005) ---

def test_weight_produces_the_correct_line_total():
    # 0.750 kg of chana at Rs 480/kg = Rs 360, exactly
    assert pricing.compute_line_total_from_quantity(750, 48_000) == 36_000


def test_weight_line_total_rounds_half_up_once_at_the_line():
    # 0.4166.. kg at Rs 480/kg -> Rs 200.16 -> Rs 200 ; here 417 milli -> Rs 200.16
    assert pricing.compute_line_total_from_quantity(417, 48_000) == 20_000
    # Rs 17/unit, 0.500 -> Rs 8.50 -> Rs 9
    assert pricing.compute_line_total_from_quantity(500, 1_700) == 900


# --- by amount -> weight (ADR-0005 / ADR-0007) ---

def test_amount_produces_the_correct_weight():
    # "Rs 200 of chana" at Rs 480/kg -> 416.66.. -> 417 milli
    assert pricing.compute_quantity_from_amount(20_000, 48_000) == 417


def test_amount_of_zero_price_is_rejected():
    with pytest.raises(ValueError):
        pricing.compute_quantity_from_amount(20_000, 0)


def test_the_two_modes_agree_within_the_rounding_rule():
    # derive weight from Rs 200, then price that weight back: within half a rupee
    unit = 48_000
    milli = pricing.compute_quantity_from_amount(20_000, unit)
    priced_back = pricing.compute_line_total_from_quantity(milli, unit)
    assert abs(priced_back - 20_000) <= 50  # <= half a rupee


# --- authoritative typed amount (ADR-0007) ---

def test_manual_amount_line_stores_exactly_what_was_typed():
    total = pricing.line_total_paisa_for(
        quantity_source="manual_amount",
        quantity_milli=417,          # derived, not used for the money
        unit_price_paisa=48_000,
        typed_amount_paisa=20_000,
    )
    assert total == 20_000  # not 20_016 from 417 * 480 / 1000


def test_manual_amount_line_without_an_amount_is_an_error():
    with pytest.raises(ValueError):
        pricing.line_total_paisa_for(
            quantity_source="manual_amount",
            quantity_milli=417,
            unit_price_paisa=48_000,
            typed_amount_paisa=None,
        )


def test_stepper_line_is_computed_from_quantity():
    total = pricing.line_total_paisa_for(
        quantity_source="stepper",
        quantity_milli=3_000,
        unit_price_paisa=17_000,
        typed_amount_paisa=None,
    )
    assert total == 51_000


# --- cart subtotal ---

def test_cart_subtotal_sums_already_rounded_lines():
    assert pricing.cart_subtotal_paisa([36_000, 20_000, 51_000]) == 107_000


def test_every_line_total_is_a_whole_rupee():
    for milli in range(1, 3_000, 13):
        assert is_whole_rupee(
            pricing.compute_line_total_from_quantity(milli, 4_900)
        )
