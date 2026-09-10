"""Invoice number formatting and the yearly-reset rule (ADR-0016).

Pure by ADR-0003 §3 — deterministic functions over plain values, no I/O. The
*atomic* claim against the ``invoice_counter`` row lives in ``sales_service`` (the
one place that also opens the sale transaction it must be part of); this module
owns the format and the rollover arithmetic, which is the part most worth testing
exhaustively.

Format: ``INV-2025-0001`` — prefix, calendar year, then a gap-free sequence that
**resets to 1 on the first sale of each calendar year** (ADR-0016 addendum).
"""
from __future__ import annotations

from dataclasses import dataclass


def format_invoice_number(prefix: str, year: int, sequence: int) -> str:
    """``INV`` + ``2025`` + ``0001`` -> ``INV-2025-0001``. The sequence is
    zero-padded to at least four digits and grows past that without breaking."""
    return f"{prefix}-{year:04d}-{sequence:04d}"


@dataclass(frozen=True)
class CounterClaim:
    """The outcome of claiming one number from the counter.

    ``sequence`` is the number this sale takes. ``next_year`` / ``next_sequence``
    are what the counter row should hold afterwards.
    """

    sequence: int
    next_year: int
    next_sequence: int


def compute_next_counter(
    *, stored_year: int, stored_sequence: int, now_year: int
) -> CounterClaim:
    """Given the counter's current state and the current calendar year, work out
    which number this sale claims and what the counter becomes.

    Same year: take ``stored_sequence``, advance to ``stored_sequence + 1``.
    New year: the sequence resets — take ``1``, advance to ``2``, adopt the new
    year. A quiet year with no sales still rolls over on the first sale of the
    next one; the counter is not touched at midnight.
    """
    if now_year != stored_year:
        return CounterClaim(sequence=1, next_year=now_year, next_sequence=2)
    return CounterClaim(
        sequence=stored_sequence,
        next_year=stored_year,
        next_sequence=stored_sequence + 1,
    )
