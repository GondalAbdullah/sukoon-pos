"""The permission catalogue (ADR-0008 §3, §4, ADR-0017).

Only the permissions ADR-0008 *confirmed* are seeded. Actions ADR-0008 explicitly
defers to the Phase 3 STOP AND ASK gate (voiding a sale, creating/deleting a
product, stock-in/out, adjusting a ledger entry, recording a Khata payment,
exporting data) are deliberately absent — they get their codes when they get their
decision, not before.
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
    "sale.refund": "Process a refund or return (ADR-0008: Admin only, step-up)",
}

# role -> the codes it holds. Admin holds every code; Cashier holds the subset
# that is not marked Admin-only in ADR-0008 §4.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_CASHIER: {
        "sale.ring",
        "sale.take_payment",
        "product.scan",
        "product.create_provisional",
    },
    ROLE_ADMIN: set(PERMISSIONS),
}

# Destructive actions that require a fresh password re-entry at the moment of the
# action, even for an Admin (ADR-0008 §5).
STEP_UP_PERMISSIONS: frozenset[str] = frozenset(
    {"product.edit_price", "sale.refund"}
)
