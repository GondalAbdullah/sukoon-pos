"""Phone number normalisation (ADR-0013 §2). Pure — no database, no Flask.

The same number is written many ways (``0300 5541298``, ``+92 300 5541298``,
``0092-300-5541298``); stored as typed, none of them match. ``normalise_phone``
resolves them to one canonical E.164 string (``+923005541298``) used for duplicate
matching and, later, message delivery. A number that can't be read with confidence
returns ``None`` — never a guess: a guessed number would send a stranger someone's
balance.
"""
from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-().]")


def normalise_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = _SEPARATORS.sub("", raw.strip())
    if not text:
        return None

    international = text.startswith("+") or text.startswith("00")
    digits = text.lstrip("+")
    if text.startswith("00"):
        digits = text[2:]
    if not digits.isdigit():
        return None

    if international:
        if digits.startswith("92"):
            return _pakistani(digits[2:])
        # another country: a country code never starts with 0; beyond that, accept
        # a plausible E.164 length and nothing more clever
        if digits.startswith("0"):
            return None
        return f"+{digits}" if 8 <= len(digits) <= 15 else None

    if digits.startswith("92") and len(digits) == 12:  # 923005541298, no plus
        return _pakistani(digits[2:])
    if digits.startswith("0"):
        return _pakistani(digits[1:])
    return None  # a bare local number with no leading 0 is ambiguous


def _pakistani(national: str) -> str | None:
    """``national`` is the number after +92 / 0. Mobiles are 3XX XXXXXXX (10
    digits); landlines are an area code plus subscriber number (9–10 digits, not
    starting 0 or 3)."""
    if national.startswith("3"):
        return f"+92{national}" if len(national) == 10 else None
    if national[:1] in "12456789" and 9 <= len(national) <= 10:
        return f"+92{national}"
    return None


def display_phone(normalised: str | None, raw: str | None) -> str:
    """How a number is shown: the customer's own spelling if they gave one."""
    return raw or normalised or ""
