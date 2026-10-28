"""Cart and line-total arithmetic (ADR-0004, ADR-0005, ADR-0007).

Pure by ADR-0003 §3. Two entry directions for a loose product produce one sale
line (ADR-0005):

* **by weight** — the cashier types kg, the line total follows from the unit price
* **by amount** — the cashier types rupees, the weight follows; the typed rupees
  are authoritative and are *not* recomputed (ADR-0007)

Lines are exact to the paisa, and so is the bill: no rounding anywhere (ADR-0046, replacing
ADR-0045's rounded total and ADR-0007's rounding at the line). There is no discount in v1
(ADR-0008 / ADR-0020), so the total is the sum of the lines.
"""
from __future__ import annotations

from sukoon.services.money import line_total_exact

_MILLI = 1000


def compute_line_total_from_quantity(
    quantity_milli: int, unit_price_paisa: int
) -> int:
    """Line total for a quantity-driven line, exact to the paisa (ADR-0046). Used for
    ``stepper`` and ``manual_weight``. ``money.line_total_exact`` in ADR-0005's argument
    order."""
    return line_total_exact(unit_price_paisa, quantity_milli)


def compute_quantity_from_amount(amount_paisa: int, unit_price_paisa: int) -> int:
    """Weight (in milli-units) implied by a typed rupee amount, rounded half-up to
    the nearest milli-unit. The money the customer asked for is exact; this weight
    is 'what the scale approximately showed' (ADR-0007)."""
    if unit_price_paisa <= 0:
        raise ValueError("unit price must be positive to derive a weight")
    numerator = amount_paisa * _MILLI
    sign = -1 if numerator < 0 else 1
    whole, remainder = divmod(abs(numerator), unit_price_paisa)
    if remainder * 2 >= unit_price_paisa:
        whole += 1
    return sign * whole


def line_total_paisa_for(
    *,
    quantity_source: str,
    quantity_milli: int,
    unit_price_paisa: int,
    typed_amount_paisa: int | None = None,
) -> int:
    """The authoritative line total for a cart line.

    ``manual_amount`` -> exactly the rupees the cashier typed (ADR-0007); every
    other source -> computed from the quantity. On a ``manual_amount`` line the
    identity ``line_total == round(quantity_milli * unit_price / 1000)`` does not
    hold, and that is deliberate — ``quantity_source`` is what explains it.
    """
    if quantity_source == "manual_amount":
        if typed_amount_paisa is None:
            raise ValueError("a manual_amount line needs the typed amount")
        return typed_amount_paisa
    return compute_line_total_from_quantity(quantity_milli, unit_price_paisa)


def cart_subtotal_paisa(line_totals_paisa: list[int]) -> int:
    """Sum of the line totals, paisa included: the receipt's lines add up to it exactly."""
    return sum(line_totals_paisa)


def compute_bill_total_paisa(subtotal_paisa: int) -> int:
    """What is paid: exactly the subtotal, paisa included (ADR-0046). Kept as the one place
    that says so, should the shop ever want its bills rounded again."""
    return subtotal_paisa
