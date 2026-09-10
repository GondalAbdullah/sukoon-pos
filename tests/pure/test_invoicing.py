"""Pure tests for invoice-number formatting and the yearly-reset rule (ADR-0016)."""
from __future__ import annotations

from sukoon.services import invoicing


def test_format_pads_to_four_digits():
    assert invoicing.format_invoice_number("INV", 2025, 1) == "INV-2025-0001"
    assert invoicing.format_invoice_number("INV", 2025, 413) == "INV-2025-0413"


def test_format_grows_past_four_digits_without_breaking():
    assert invoicing.format_invoice_number("INV", 2025, 12345) == "INV-2025-12345"


def test_same_year_takes_the_stored_sequence_and_advances():
    claim = invoicing.compute_next_counter(
        stored_year=2025, stored_sequence=42, now_year=2025
    )
    assert (claim.sequence, claim.next_year, claim.next_sequence) == (42, 2025, 43)


def test_new_year_resets_to_one():
    claim = invoicing.compute_next_counter(
        stored_year=2024, stored_sequence=907, now_year=2025
    )
    assert (claim.sequence, claim.next_year, claim.next_sequence) == (1, 2025, 2)


def test_a_quiet_year_still_rolls_over_on_the_first_sale():
    # counter last touched in 2023; first sale is in 2025
    claim = invoicing.compute_next_counter(
        stored_year=2023, stored_sequence=5, now_year=2025
    )
    assert claim.sequence == 1
    assert claim.next_year == 2025


def test_first_ever_sequence_of_a_fresh_counter():
    claim = invoicing.compute_next_counter(
        stored_year=2025, stored_sequence=1, now_year=2025
    )
    assert claim.sequence == 1
    assert claim.next_sequence == 2
