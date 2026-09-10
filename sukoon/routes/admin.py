"""Admin-only surface.

Phase 1 ships no real admin screens yet — the CRUD they guard arrives in Phase 2.
What exists now is the *enforcement seam*: a permission-guarded probe route that
the Phase 1 authorization tests hit to prove a Cashier gets a real server-side 403
(ADR-0008 §4, Development Specification Phase 1 Required Tests).
"""
from __future__ import annotations

from flask import Blueprint
from flask_login import login_required

from sukoon.routes.guards import permission_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/price-check")
@login_required
@permission_required("product.edit_price")
def price_check():
    """Stand-in for the Phase 2 price-edit screen. Guarded by the same Admin-only
    permission that screen will use. Returns HTML, never JSON (ADR-0001)."""
    return "<p>admin area reached</p>"
