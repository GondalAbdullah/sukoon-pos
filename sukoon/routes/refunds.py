"""Returns and refunds (Development Specification Phase 3 step 6; ADR-0020).

Thin (ADR-0003 §2). A Cashier initiates against an existing invoice
(``sale.refund_initiate``); an Admin approves with a step-up password
(``sale.refund``). Every rule — refundable quantity, whole-rupee line totals,
stock restock, ledger reversal, the sale-status transition — lives in
``refund_service``.
"""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from sukoon.extensions import db
from sukoon.models import Sale
from sukoon.routes.guards import permission_required, require_step_up
from sukoon.services import refund_service
from sukoon.services.refund_service import RefundLineSpec

bp = Blueprint("refunds", __name__, url_prefix="/refunds")


def _qty_to_milli(raw: str | None) -> int:
    if not raw or not raw.strip():
        return 0
    try:
        return max(0, round(float(raw) * 1000))
    except ValueError:
        return 0


# --- initiate (Cashier) ------------------------------------------------


@bp.route("/find")
@login_required
@permission_required("sale.refund_initiate")
def find():
    invoice = (request.args.get("invoice") or "").strip()
    sale = None
    if invoice:
        sale = db.session.scalar(db.select(Sale).where(Sale.invoice_number == invoice))
        if sale is None:
            flash(f"No sale found for “{invoice}”.", "error")
    return render_template("refunds/find.html", invoice=invoice, sale=sale)


@bp.route("/sale/<int:sale_id>")
@login_required
@permission_required("sale.refund_initiate")
def for_sale(sale_id: int):
    sale = db.session.get(Sale, sale_id) or abort(404)
    lines = [
        {
            "item": item,
            "refundable_milli": refund_service.refundable_quantity_milli(item),
            "whole_line_only": item.quantity_source == "manual_amount",
        }
        for item in sale.items
    ]
    return render_template(
        "refunds/sale.html",
        sale=sale,
        lines=lines,
        existing=refund_service.refunds_for_sale(sale.id),
    )


@bp.route("", methods=["POST"])
@login_required
@permission_required("sale.refund_initiate")
def initiate():
    sale_id = int(request.form.get("sale_id", 0))
    sale = db.session.get(Sale, sale_id) or abort(404)

    specs: list[RefundLineSpec] = []
    for item in sale.items:
        qty = _qty_to_milli(request.form.get(f"qty_{item.id}"))
        if qty <= 0:
            continue
        specs.append(
            RefundLineSpec(
                sale_item_id=item.id,
                quantity_milli=qty,
                restock=request.form.get(f"restock_{item.id}") == "on",
            )
        )

    try:
        refund = refund_service.initiate_refund(
            sale_id=sale.id,
            lines=specs,
            reason=request.form.get("reason", ""),
            initiated_by_user_id=current_user.id,
        )
    except refund_service.RefundError as exc:
        flash(str(exc), "error")
        return redirect(url_for("refunds.for_sale", sale_id=sale.id))

    flash(
        f"Refund of {refund.total_paisa // 100} rupees recorded — waiting for an "
        "Admin to approve it.",
        "info",
    )
    return redirect(url_for("refunds.for_sale", sale_id=sale.id))


# --- approve / reject (Admin, step-up) -------------------------------


@bp.route("/pending")
@login_required
@permission_required("sale.refund")
def pending():
    return render_template(
        "refunds/pending.html", refunds=refund_service.list_pending()
    )


@bp.route("/<int:refund_id>/approve", methods=["POST"])
@login_required
@permission_required("sale.refund")
def approve(refund_id: int):
    require_step_up()
    try:
        refund_service.approve_refund(
            refund_id=refund_id, approved_by_user_id=current_user.id
        )
        flash("Refund approved.", "info")
    except refund_service.RefundError as exc:
        flash(str(exc), "error")
    return redirect(url_for("refunds.pending"))


@bp.route("/<int:refund_id>/reject", methods=["POST"])
@login_required
@permission_required("sale.refund")
def reject(refund_id: int):
    try:
        refund_service.reject_refund(
            refund_id=refund_id, approved_by_user_id=current_user.id
        )
        flash("Refund rejected.", "info")
    except refund_service.RefundError as exc:
        flash(str(exc), "error")
    return redirect(url_for("refunds.pending"))
