"""Money arithmetic and the rupee boundary (ADR-0007).

Money is stored as an integer count of paisa everywhere (Operating Rule 8). Paisa
is the *storage* unit; the rupee is the *transaction* unit — every persisted money
value is a whole number of rupees, i.e. a multiple of 100 paisa.

Rounding happens exactly **once, at the line**, half-up, away from zero so a refund
mirrors its sale. This module holds that rule and nothing else — no Flask, no DB.

Product prices may carry paisa (ADR-0044), and since ADR-0046 so does everything built from
them: line totals, the bill, cash and change, the Khata. Nothing is rounded to the rupee any
more, except a weighed line's fraction of a paisa (to the paisa) and the estimated cost figures
in reports.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

RUPEE_PAISA = 100


def round_paisa_to_rupee(paisa: int) -> int:
    """Round an integer paisa amount to the nearest whole rupee.

    Half-up, and symmetric about zero: ``round(50) == 100`` and
    ``round(-50) == -100``, so a refund line is the exact negative of its sale
    line. Rs 159.50 becomes Rs 160 — what a person at a counter expects
    (ADR-0007), not banker's rounding.
    """
    sign = -1 if paisa < 0 else 1
    whole, remainder = divmod(abs(paisa), RUPEE_PAISA)
    if remainder * 2 >= RUPEE_PAISA:
        whole += 1
    return sign * whole * RUPEE_PAISA


def line_total_exact(unit_price_paisa: int, quantity_milli: int) -> int:
    """A line's total exact to the paisa (ADR-0046): ``unit price × quantity``, rounded
    half-up to the paisa (only a weighed quantity leaves a fraction of one), symmetric about
    zero so a refund line mirrors its sale line. 3 × Rs 150.50 is Rs 451.50."""
    milli_paisa = unit_price_paisa * quantity_milli  # exact: paisa × 1000
    sign = -1 if milli_paisa < 0 else 1
    whole, remainder = divmod(abs(milli_paisa), 1000)
    if remainder * 2 >= 1000:
        whole += 1
    return sign * whole


def is_whole_rupee(paisa: int) -> bool:
    """True if ``paisa`` is an exact multiple of 100 — the invariant every
    persisted money column must satisfy (ADR-0007)."""
    return paisa % RUPEE_PAISA == 0


def line_total_for_quantity(unit_price_paisa: int, quantity_milli: int) -> int:
    """Line total for a quantity-driven line (``stepper`` / ``manual_weight``).

    Quantity is integer milli-units (ADR-0004). The exact product
    ``unit_price_paisa × quantity_milli / 1000`` is rounded to the nearest rupee
    in a single half-up step (no intermediate rounding to paisa), so the result
    is symmetric for a refund. ``manual_amount`` lines do **not** use this — there
    the typed amount is authoritative and is stored as-is (ADR-0007).
    """
    milli_paisa = unit_price_paisa * quantity_milli  # exact: paisa × 1000
    sign = -1 if milli_paisa < 0 else 1
    one_rupee = RUPEE_PAISA * 1000
    whole, remainder = divmod(abs(milli_paisa), one_rupee)
    if remainder * 2 >= one_rupee:
        whole += 1
    return sign * whole * RUPEE_PAISA


# A hundred crore rupees: far above anything a shop prices, far below SQLite's integer limit.
_MAX_PAISA = 100 * 1_000_000_000


def parse_rupees(raw: str | None) -> int | None:
    """Rupees as typed (``"105.50"``, ``"1,050"``) to exact integer paisa, or ``None`` if blank.

    Exact, through ``Decimal`` — never a float. More than two decimals is refused with
    ``ValueError`` rather than rounded, so what was typed is what is stored (ADR-0044 §1)."""
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Enter an amount in rupees.") from exc
    if not value.is_finite():
        raise ValueError("Enter an amount in rupees.")
    paisa = value * 100
    if paisa != paisa.to_integral_value():
        raise ValueError("Use at most two decimals (paisa).")
    if abs(paisa) >= _MAX_PAISA:
        raise ValueError("That amount is too large.")
    return int(paisa)


def format_rupees(paisa: int | None, *, prefix: str = "Rs ") -> str:
    """``Rs 1,050`` for a whole amount, ``Rs 105.50`` when there are paisa (ADR-0044 §4)."""
    if paisa is None:
        return "—"
    sign = "-" if paisa < 0 else ""
    whole, part = divmod(abs(paisa), RUPEE_PAISA)
    return f"{sign}{prefix}{whole:,}" + (f".{part:02d}" if part else "")


def rupees_input_value(paisa: int | None) -> str:
    """A price as it goes back into an input box: ``105.50``, ``1050``, or empty."""
    if paisa is None:
        return ""
    whole, part = divmod(paisa, RUPEE_PAISA)
    return f"{whole}.{part:02d}" if part else str(whole)
