"""Issuing a receipt — the ESC/POS print, and the PDF the shop falls back to
(Development Specification Phase 3 step 5).

``issue_receipt`` is the one entry point the till uses: it tries the thermal
printer and, on any failure, reports that a PDF should be offered instead. It
never raises — a sale is already committed by the time a receipt is printed, and
"a printer being offline degrades to PDF and never blocks completing the sale"
(Development Spec §11 Phase 3). No Flask import (ADR-0003 §1).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sukoon.models import Sale
from sukoon.services.receipts import printer
from sukoon.services.receipts.receipt import build_receipt, render_escpos, render_pdf

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReceiptOutcome:
    printed: bool  # True -> a thermal receipt came out
    medium: str  # 'thermal' | 'pdf'
    detail: str | None = None  # why the fallback happened, if it did


def issue_receipt(sale: Sale) -> ReceiptOutcome:
    """Print the receipt for ``sale``. Falls back to "offer the PDF" on any
    printer problem. Never raises."""
    data = build_receipt(sale)
    try:
        printer.send(render_escpos(data))
        return ReceiptOutcome(printed=True, medium="thermal")
    except printer.PrinterUnavailable as exc:
        log.info("receipt for %s -> PDF fallback: %s", sale.invoice_number, exc)
        return ReceiptOutcome(printed=False, medium="pdf", detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive; must never bubble up
        log.warning("receipt for %s: unexpected %s", sale.invoice_number, exc)
        return ReceiptOutcome(printed=False, medium="pdf", detail="unexpected error")


def receipt_pdf(sale: Sale) -> bytes:
    """The 80 mm PDF receipt for ``sale`` — served on demand, never stored."""
    return render_pdf(build_receipt(sale))
