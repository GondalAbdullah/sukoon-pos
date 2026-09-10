"""Money arithmetic and the rupee boundary (ADR-0007).

Money is stored as an integer count of paisa everywhere (Operating Rule 8). Paisa
is the *storage* unit; the rupee is the *transaction* unit — every persisted money
value is a whole number of rupees, i.e. a multiple of 100 paisa.

Rounding happens exactly **once, at the line**, half-up, away from zero so a refund
mirrors its sale. This module holds that rule and nothing else — no Flask, no DB.
"""
from __future__ import annotations

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
