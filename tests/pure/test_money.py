"""Pure unit tests for the rupee boundary (ADR-0007). No DB, no app context.

The ADR asks for exhaustive boundary tests on ``round_paisa_to_rupee`` and for the
symmetry that makes a refund the exact negative of its sale.
"""
from __future__ import annotations

import pytest

from sukoon.services.money import (
    is_whole_rupee,
    line_total_for_quantity,
    round_paisa_to_rupee,
)


@pytest.mark.parametrize(
    "paisa,expected",
    [
        (0, 0),
        (1, 0),
        (49, 0),
        (50, 100),   # half rounds up
        (51, 100),
        (99, 100),
        (100, 100),
        (149, 100),
        (150, 200),  # half rounds up
        (151, 200),
    ],
)
def test_round_paisa_to_rupee_boundaries(paisa, expected):
    assert round_paisa_to_rupee(paisa) == expected


@pytest.mark.parametrize("paisa", [0, 1, 49, 50, 51, 99, 100, 149, 150, 12345, 999999])
def test_round_is_symmetric_about_zero(paisa):
    """A refund mirrors its sale: round(-x) == -round(x)."""
    assert round_paisa_to_rupee(-paisa) == -round_paisa_to_rupee(paisa)


def test_round_negative_half_goes_away_from_zero():
    assert round_paisa_to_rupee(-50) == -100
    assert round_paisa_to_rupee(-49) == 0
    assert round_paisa_to_rupee(-150) == -200


def test_round_output_is_always_a_whole_rupee():
    for paisa in range(-500, 501):
        assert is_whole_rupee(round_paisa_to_rupee(paisa))


def test_is_whole_rupee():
    assert is_whole_rupee(0)
    assert is_whole_rupee(15000)
    assert is_whole_rupee(-15000)
    assert not is_whole_rupee(15050)
    assert not is_whole_rupee(1)


# --- line totals (ADR-0007: round once, at the line) ---

def test_line_total_exact_when_arithmetic_is_clean():
    # kidney beans Rs 480/kg, 417 g -> Rs 200.16 -> Rs 200
    assert line_total_for_quantity(48_000, 417) == 20_000


def test_line_total_rounds_half_up_once():
    # Rs 17/unit, 500 milli -> Rs 8.50 -> Rs 9
    assert line_total_for_quantity(1_700, 500) == 900
    # Rs 17/unit, 499 milli -> Rs 8.483 -> Rs 8
    assert line_total_for_quantity(1_700, 499) == 800


def test_line_total_whole_units_are_untouched():
    assert line_total_for_quantity(17_000, 3_000) == 51_000  # 3 bags at Rs 170


def test_line_total_is_symmetric_for_a_refund():
    assert line_total_for_quantity(48_000, -417) == -line_total_for_quantity(48_000, 417)


def test_line_total_is_always_a_whole_rupee():
    for milli in range(1, 2_000, 7):
        assert is_whole_rupee(line_total_for_quantity(4_900, milli))
