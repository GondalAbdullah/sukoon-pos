"""The weigh box's on-screen previews (ADR-0005, ADR-0007).

The till shows the cashier a preview before they press Set: type a weight and it shows the rupees,
type an amount and it shows the weight. Those two sums live in the page, in Alpine, where the
Python tests cannot reach them — and one of them was wrong for the whole of Phase 3: it read
``amount * 1000 / unitPrice`` and showed **ten times** the weight. The sale was always right,
because the server does its own conversion, but the cashier saw a number that did not match what
the customer got (found on the VM, 2026-09-18).

The units are the trap: the typed amount is in **rupees**, the price is in **paisa**, the weight is
in **kg**. So this asserts the two multipliers, and checks them against the server's own arithmetic.
"""
from __future__ import annotations

import re
from pathlib import Path

from sukoon.services import pricing

TILL = Path(__file__).resolve().parents[2] / "sukoon" / "templates" / "till" / "till.html"


def _multiplier(expression: str) -> int:
    template = TILL.read_text(encoding="utf-8")
    match = re.search(expression, template)
    assert match, f"the preview sum {expression!r} is no longer in the till template"
    return int(match.group(1))


def test_the_amount_preview_converts_rupees_over_paisa_into_kilograms():
    # kg = rupees * 100 / paisa. With 1000 it showed ten times the weight.
    assert _multiplier(r"this\.amount \* (\d+) / this\.unitPrice") == 100


def test_the_weight_preview_converts_kilograms_times_paisa_into_rupees():
    assert _multiplier(r"this\.weight \* this\.unitPrice / (\d+)") == 100


def test_the_preview_agrees_with_what_the_server_will_charge():
    """Rs 200 of atta at Rs 480/kg: the screen and the sale must say the same thing."""
    amount_rupees, price_paisa = 200, 48_000

    on_screen_kg = amount_rupees * _multiplier(r"this\.amount \* (\d+) / this\.unitPrice") \
        / price_paisa
    from_the_server_milli = pricing.compute_quantity_from_amount(
        amount_rupees * 100, price_paisa)
    from_the_server_kg = from_the_server_milli / 1000

    assert round(on_screen_kg, 3) == round(from_the_server_kg, 3) == 0.417
