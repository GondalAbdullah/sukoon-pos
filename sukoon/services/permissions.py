"""The permission catalogue (ADR-0008 §3/§4, ADR-0017, ADR-0019, ADR-0020).

Only permissions with an actual decision behind them are seeded. Actions still
without a decision (voiding a completed sale, adjusting a ledger entry, recording a
Khata payment, exporting data) are deliberately absent — they get their codes when
they get their decision, not before. The Phase 3 gate (ADR-0020) assigned refund:
``sale.refund_initiate`` (Cashier + Admin) starts one, ``sale.refund`` (Admin,
step-up) approves it.
"""
from __future__ import annotations

from sukoon.models.user import ROLE_ADMIN, ROLE_CASHIER

# code -> human description
PERMISSIONS: dict[str, str] = {
    "sale.ring": "Ring up a sale and add items to a cart",
    "sale.take_payment": "Take cash, card, or credit payment for a sale",
    "product.scan": "Resolve a scanned barcode at the till",
    "product.create_provisional": "Create a provisional product at the till (ADR-0011)",
    "product.edit_price": "Edit a product's selling price (ADR-0008: Admin only, step-up)",
    "sale.refund_initiate": "Start a refund against an existing sale (ADR-0020)",
    "sale.refund": "Approve or reject a pending refund (ADR-0020: Admin only, step-up)",
    "catalog.manage": "Create, edit, or delete products, categories, and barcodes (ADR-0019)",
    "stock.adjust": "Record stock-in, stock-out, and count corrections (ADR-0019)",
}

# role -> the codes it holds. Admin holds every code; Cashier holds the subset
# that is not Admin-only in ADR-0008 §4 / ADR-0019.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_CASHIER: {
        "sale.ring",
        "sale.take_payment",
        "product.scan",
        "product.create_provisional",
        "sale.refund_initiate",
    },
    ROLE_ADMIN: set(PERMISSIONS),
}

# Destructive actions that require a fresh password re-entry at the moment of the
# action, even for an Admin (ADR-0008 §5). Creating a price-override barcode is
# also step-up (ADR-0009) but is gated in its route, not by a permission code.
STEP_UP_PERMISSIONS: frozenset[str] = frozenset(
    {"product.edit_price", "sale.refund"}
)
