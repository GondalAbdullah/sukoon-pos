"""Stock → Import: upload a product spreadsheet, decide about it, add it, then scan barcodes on
(ADR-0043).

Thin (ADR-0003 §2): parse, call ``catalog_import_service``, render. Everything here is
``catalog.manage`` (Admin, ADR-0019); a changed selling price on the worklist additionally
needs ``product.edit_price`` and the password again (ADR-0008 §5).
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from sukoon.routes.guards import permission_required
from sukoon.routes.stock import _int_or_none, _qty_to_milli, _rupees_to_paisa
from sukoon.services import auth_service
from sukoon.services import catalog_import_service as imp
from sukoon.services import inventory_service as inv
from sukoon.services.auth_service import role_has_permission

bp = Blueprint("catalog_import", __name__, url_prefix="/stock/import")

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_WORKLIST_PAGE = 25


def _batch(import_id: int):
    return imp.get_import(import_id) or abort(404)


@bp.route("/", methods=["GET", "POST"])
@login_required
@permission_required("catalog.manage")
def index():
    if request.method == "POST":
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            flash("Choose the spreadsheet (.csv) to import.", "error")
            return redirect(url_for("catalog_import.index"))
        data = upload.read(_MAX_UPLOAD_BYTES + 1)
        if len(data) > _MAX_UPLOAD_BYTES:
            flash("That file is too large for a product list (over 5 MB).", "error")
            return redirect(url_for("catalog_import.index"))
        try:
            batch = imp.create_import(filename=upload.filename, data=data,
                                      user_id=current_user.id)
        except inv.InventoryError as exc:
            flash(str(exc), "error")
            return redirect(url_for("catalog_import.index"))
        flash(f"{len(batch.rows):,} rows read from {batch.filename}. Nothing is in stock yet — "
              "check them below, then add them.", "info")
        return redirect(url_for("catalog_import.review", import_id=batch.id))
    batches = imp.list_imports()
    return render_template("stock/import_index.html", batches=batches,
                           summaries={b.id: imp.compute_summary(b) for b in batches})


@bp.route("/<int:import_id>")
@login_required
@permission_required("catalog.manage")
def review(import_id: int):
    batch = _batch(import_id)
    return render_template(
        "stock/import_review.html",
        batch=batch,
        summary=imp.compute_summary(batch),
        groups=imp.groups_to_choose(batch),
        needs_price=imp.rows_with_status(batch, "needs_price"),
        skipped=imp.rows_with_status(batch, "skipped"),
        flagged=imp.ready_rows_flagged(batch),
        cost_above_price=imp.compute_cost_above_price,
    )


@bp.route("/<int:import_id>/choose", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def choose(import_id: int):
    batch = _batch(import_id)
    keep = {i for i in (_int_or_none(v) for v in request.form.getlist("keep")) if i is not None}
    if not keep and not request.form.get("skip_all"):
        flash("Tick the row to keep, or choose “Skip all of these”.", "error")
        return redirect(url_for("catalog_import.review", import_id=import_id) + "#choose")
    try:
        kept = imp.choose_from_group(batch, request.form.get("group", ""), keep)
        flash(f"Kept {kept}." if kept else "Skipped the whole group.", "info")
    except inv.InventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("catalog_import.review", import_id=import_id) + "#choose")


@bp.route("/<int:import_id>/rows/<int:row_id>/<action>", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def row_action(import_id: int, row_id: int, action: str):
    batch = _batch(import_id)
    row = imp.get_row(batch, row_id) or abort(404)
    try:
        if action == "price":
            imp.set_row_price(row, _rupees_to_paisa(request.form.get("sell_price")))
            flash(f"{row.name}: priced, ready to add.", "info")
        elif action == "skip":
            imp.skip_row(row)
        elif action == "restore":
            imp.restore_row(row)
            flash(f"{row.name} is back in the list.", "info")
        else:
            abort(404)
    except inv.InventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("catalog_import.review", import_id=import_id))


@bp.route("/<int:import_id>/add", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def add_to_stock(import_id: int):
    batch = _batch(import_id)
    added = imp.add_ready_to_stock(batch, user_id=current_user.id)
    if not added:
        flash("Nothing is ready to add.", "error")
        return redirect(url_for("catalog_import.review", import_id=import_id))
    flash(f"{added:,} products added to stock. Now scan their barcodes on.", "info")
    return redirect(url_for("catalog_import.worklist", import_id=import_id))


@bp.route("/<int:import_id>/undo", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def undo(import_id: int):
    batch = _batch(import_id)
    deleted, deactivated = imp.undo_import(batch)
    msg = f"Undone: {deleted:,} products removed."
    if deactivated:
        msg += (f" {deactivated:,} had already been sold or counted, so they were "
                "deactivated instead of removed.")
    flash(msg, "info")
    return redirect(url_for("catalog_import.review", import_id=import_id))


# --- the worklist -----------------------------------------------------------------------

def _worklist_args() -> dict:
    show = request.values.get("show")
    page = max(1, _int_or_none(request.values.get("page")) or 1)
    return {"show": show if show in imp.WORKLIST_FILTERS else "no_barcode",
            "q": (request.values.get("q") or "").strip(), "page": page}


@bp.route("/<int:import_id>/products")
@login_required
@permission_required("catalog.manage")
def worklist(import_id: int):
    batch = _batch(import_id)
    args = _worklist_args()
    entries, total = imp.list_worklist(batch, show=args["show"], query=args["q"],
                                       limit=_WORKLIST_PAGE,
                                       offset=(args["page"] - 1) * _WORKLIST_PAGE)
    return render_template(
        "stock/import_worklist.html",
        batch=batch, entries=entries, total=total, page_size=_WORKLIST_PAGE,
        counts=imp.compute_worklist_counts(batch),
        categories=inv.list_categories(),
        can_price=role_has_permission(current_user.role, "product.edit_price"),
        has_barcode=imp.product_has_barcode,
        cost_was_rounded=imp.compute_cost_was_rounded,
        cost_above_price=imp.compute_cost_above_price,
        **args,
    )


def _stock_count(product, raw: str | None) -> int | None:
    """The shelf count typed on the worklist, or None to leave stock alone. Counting stock is
    ``stock.adjust`` (ADR-0019); an Admin has it, and the worklist is Admin-only anyway."""
    if raw is None or not raw.strip():
        return None
    if not role_has_permission(current_user.role, "stock.adjust"):
        abort(403)
    return _qty_to_milli(raw)


@bp.route("/<int:import_id>/products/<int:product_id>", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def save_product(import_id: int, product_id: int):
    batch = _batch(import_id)
    args = _worklist_args()
    back = url_for("catalog_import.worklist", import_id=import_id, show=args["show"],
                   q=args["q"] or None, page=args["page"])
    product = inv.get_product(product_id) or abort(404)
    if not any(r.product_id == product.id for r in batch.rows):
        abort(404)
    f = request.form
    try:
        sell = _rupees_to_paisa(f.get("sell_price"))
        if sell is not None and sell != product.sell_price_paisa:
            # ADR-0008 §5: a price change is a price change, imported or not
            if not role_has_permission(current_user.role, "product.edit_price"):
                abort(403)
            if not auth_service.verify_step_up(current_user, f.get("step_up_password", "")):
                raise inv.ValidationError(
                    f"{product.name}: changing the selling price needs your password. "
                    "Nothing was saved.")
        code = imp.save_worklist_product(
            product,
            name=f.get("name"),
            category_id=_int_or_none(f.get("category_id")),
            cost_price_paisa=_rupees_to_paisa(f.get("cost_price")),
            sell_price_paisa=sell,
            low_stock_threshold_milli=_qty_to_milli(f.get("low_stock_threshold")),
            barcode=f.get("barcode"),
            user_id=current_user.id,
            stock_milli=_stock_count(product, f.get("stock")),
        )
    except inv.InventoryError as exc:
        flash(str(exc), "error")
        return redirect(back + f"#p{product_id}")
    flash(f"{product.name}: barcode {code.barcode} attached." if code
          else f"{product.name}: saved.", "info")
    return redirect(back)
