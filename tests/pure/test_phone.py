"""ADR-0013 §2 — phone normalisation, boundary-tested."""
from __future__ import annotations

import pytest

from sukoon.services.phone import normalise_phone


@pytest.mark.parametrize("raw", [
    "0300 5541298", "03005541298", "+92 300 5541298", "+923005541298",
    "0092 300 5541298", "0092-300-5541298", "923005541298", "(0300) 554-1298",
    "  0300.554.1298  ",
])
def test_every_spelling_of_one_mobile_is_the_same_number(raw):
    assert normalise_phone(raw) == "+923005541298"


@pytest.mark.parametrize("raw,expected", [
    ("042 35761234", "+924235761234"),   # Lahore landline, 10-digit national
    ("051 2345678", "+92512345678"),     # Islamabad, 9-digit national
    ("+971 50 123 4567", "+971501234567"),  # abroad: plausible E.164 kept
])
def test_landlines_and_foreign_numbers(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "", "   ", "abc", "0300 554129", "0300 55412981",  # mobile one digit short / long
    "3005541298",            # no leading 0 or +92: ambiguous, not guessed
    "0000000000", "0300-55A-1298", "+92", "+1234", "0092",
])
def test_unreadable_numbers_are_none_never_guessed(raw):
    assert normalise_phone(raw) is None
