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


# --- paisa in product prices (ADR-0044) ---------------------------------------------------

from sukoon.services.money import format_rupees, parse_rupees, rupees_input_value  # noqa: E402


@pytest.mark.parametrize("raw, paisa", [
    ("105.50", 10550), ("105.5", 10550), ("1,050", 105000), (" 4.3 ", 430), ("0", 0),
    ("0.01", 1), ("", None), (None, None), ("   ", None),
])
def test_parse_rupees_is_exact(raw, paisa):
    assert parse_rupees(raw) == paisa


@pytest.mark.parametrize("raw", ["105.505", "abc", "1e400", "nan", "inf"])
def test_parse_rupees_refuses_a_third_decimal_or_nonsense(raw):
    with pytest.raises(ValueError):
        parse_rupees(raw)


def test_parse_rupees_never_goes_through_a_float():
    # 0.1 + 0.2 style traps: 1.15 * 100 is 114.99999999999999 as a float
    assert parse_rupees("1.15") == 115 and parse_rupees("4.35") == 435


@pytest.mark.parametrize("paisa, text", [
    (105000, "Rs 1,050"), (10550, "Rs 105.50"), (430, "Rs 4.30"), (5, "Rs 0.05"),
    (0, "Rs 0"), (-10550, "-Rs 105.50"), (None, "—"),
])
def test_format_rupees_shows_paisa_only_when_there_is_some(paisa, text):
    assert format_rupees(paisa) == text


@pytest.mark.parametrize("paisa, text", [(10550, "105.50"), (105000, "1050"), (None, "")])
def test_an_input_box_gets_back_what_was_typed(paisa, text):
    assert rupees_input_value(paisa) == text
    if paisa is not None:
        assert parse_rupees(text) == paisa


def test_a_paisa_unit_price_still_makes_a_whole_rupee_line():
    assert line_total_for_quantity(10_550, 1_000) == 10_600
    assert line_total_for_quantity(10_550, 3_000) == 31_700
    assert all(is_whole_rupee(line_total_for_quantity(10_550, q)) for q in range(0, 20_000, 7))


def test_statements_and_messages_show_paisa_when_there_are_some():
    """ADR-0046: a Khata can owe Rs 721.34, and its statement and WhatsApp message say so."""
    from sukoon.services import statements
    from sukoon.services.notifications import queue

    for rs in (statements.rs, queue.rs):
        assert rs(72_134) == rs(-72_134) == "Rs 721.34"
        assert rs(1_000_000) == "Rs 10,000"
