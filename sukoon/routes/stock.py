"""Stock & catalog management (Development Specification Phase 2).

Thin by construction (ADR-0003 §2): parse the form, call ``inventory_service``,
render. No stock or money arithmetic here. Authorization per ADR-0019:
``catalog.manage`` for catalog edits, ``stock.adjust`` for movements; a sell-price
change additionally needs ``product.edit_price`` + step-up (ADR-0008).
"""
from __future__ import annotations

import io

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from sukoon.extensions import db
from sukoon.models import Category, Product, ProductBarcode
from sukoon.routes.guards import permission_required, require_step_up
from sukoon.services import inventory_service as inv
from sukoon.services.auth_service import role_has_permission
from sukoon.services.receipts import labels

bp = Blueprint("stock", __name__, url_prefix="/stock")

_PAGE_SIZE = 50


# --- form parsing helpers --------------------------------------------------

def _rupees_to_paisa(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return round(float(raw) * 100)
    except ValueError as exc:
        raise inv.ValidationError("Enter an amount in rupees.") from exc


def _qty_to_milli(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return round(float(raw) * 1000)
    except ValueError as exc:
        raise inv.ValidationError("Enter a quantity.") from exc


def _int_or_none(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# --- list ---------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    q = request.args.get("q") or None
    category_id = _int_or_none(request.args.get("category"))
    needs_completing = request.args.get("filter") == "needs_completing"
    page = max(1, _int_or_none(request.args.get("page")) or 1)

    products, total = inv.list_products(
        query=q,
        category_id=category_id,
        needs_completing=needs_completing,
        limit=_PAGE_SIZE,
        offset=(page - 1) * _PAGE_SIZE,
    )
    return render_template(
        "stock/list.html",
        products=products,
        total=total,
        page=page,
        page_size=_PAGE_SIZE,
        q=q or "",
        category_id=category_id,
        needs_completing=needs_completing,
        categories=inv.list_categories(),
        summary=inv.catalog_summary(),
        status_of=inv.compute_stock_status,
        can_manage=role_has_permission(current_user.role, "catalog.manage"),
    )


# --- products ---------------------------------------------------------

@bp.route("/products/new")
@login_required
@permission_required("catalog.manage")
def new_product():
    return render_template(
        "stock/product_form.html", product=None, categories=inv.list_categories()
    )


@bp.route("/bulk", methods=["GET", "POST"])
@login_required
@permission_required("catalog.manage")
def bulk_entry():
    """One repeated motion: scan, type, Enter, next (ADR-0011 §1). Scanning a code
    that already exists jumps to that product rather than duplicating it."""
    if request.method == "POST":
        f = request.form
        code = (f.get("barcode") or "").strip()
        if code:
            existing = inv.resolve_barcode(code)
            if existing is not None:
                flash(f"{code} already belongs to {existing.product.name}.", "info")
                return redirect(
                    url_for("stock.product_detail", product_id=existing.product.id)
                )
        try:
            category = None
            cid = _int_or_none(f.get("category_id"))
            if cid is not None:
                category = db.session.get(Category, cid) or abort(400)
            product = inv.create_product(
                name=f.get("name", ""),
                sell_price_paisa=_rupees_to_paisa(f.get("sell_price")),
                cost_price_paisa=_rupees_to_paisa(f.get("cost_price")),
                category=category,
                low_stock_threshold_milli=_qty_to_milli(f.get("low_stock_threshold")),
                created_by_user_id=current_user.id,
            )
            if code:
                inv.assign_barcode(
                    product=product, code=code, user_id=current_user.id
                )
            flash(f"{product.name} added ({product.sku}).", "info")
        except inv.InventoryError as exc:
            flash(str(exc), "error")
        return redirect(url_for("stock.bulk_entry"))

    return render_template(
        "stock/bulk_entry.html",
        categories=inv.list_categories(),
        recent=inv.list_products(limit=10)[0],
    )


@bp.route("/products", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def create_product():
    f = request.form
    try:
        category = None
        cid = _int_or_none(f.get("category_id"))
        if cid is not None:
            category = db.session.get(Category, cid) or abort(400)
        product = inv.create_product(
            name=f.get("name", ""),
            sell_price_paisa=_rupees_to_paisa(f.get("sell_price")),
            cost_price_paisa=_rupees_to_paisa(f.get("cost_price")),
            category=category,
            unit_label=f.get("unit_label", "unit"),
            allows_fractional=f.get("allows_fractional") == "on",
            low_stock_threshold_milli=_qty_to_milli(f.get("low_stock_threshold")),
            created_by_user_id=current_user.id,
        )
    except inv.InventoryError as exc:
        flash(str(exc), "error")
        return (
            render_template(
                "stock/product_form.html",
                product=None,
                categories=inv.list_categories(),
                form=f,
            ),
            400,
        )
    flash(f"{product.name} added ({product.sku}).", "info")
    return redirect(url_for("stock.product_detail", product_id=product.id))


@bp.route("/products/<int:product_id>")
@login_required
def product_detail(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    return render_template(
        "stock/product_detail.html",
        product=product,
        status=inv.compute_stock_status(product),
        movements=inv.movements_for_product(product_id),
        barcodes=inv.barcodes_for_product(product_id),
        categories=inv.list_categories(),
        can_manage=role_has_permission(current_user.role, "catalog.manage"),
        can_adjust=role_has_permission(current_user.role, "stock.adjust"),
        can_price=role_has_permission(current_user.role, "product.edit_price"),
    )


@bp.route("/products/<int:product_id>/edit")
@login_required
@permission_required("catalog.manage")
def edit_product(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    return render_template(
        "stock/product_form.html", product=product, categories=inv.list_categories()
    )


@bp.route("/products/<int:product_id>", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def update_product(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    f = request.form
    new_sell_price = _rupees_to_paisa(f.get("sell_price"))

    if new_sell_price is not None and new_sell_price != product.sell_price_paisa:
        if not role_has_permission(current_user.role, "product.edit_price"):
            abort(403)
        require_step_up()

    try:
        inv.update_product(
            product,
            name=f.get("name"),
            sell_price_paisa=new_sell_price,
            cost_price_paisa=_rupees_to_paisa(f.get("cost_price")),
            category_id=_int_or_none(f.get("category_id")),
            unit_label=f.get("unit_label"),
            allows_fractional=f.get("allows_fractional") == "on",
            low_stock_threshold_milli=_qty_to_milli(f.get("low_stock_threshold")),
            sku=f.get("sku"),
        )
    except inv.InventoryError as exc:
        flash(str(exc), "error")
        return (
            render_template(
                "stock/product_form.html",
                product=product,
                categories=inv.list_categories(),
            ),
            400,
        )
    flash("Saved.", "info")
    return redirect(url_for("stock.product_detail", product_id=product.id))


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def delete_product(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    outcome = inv.delete_product(product)
    if outcome == "soft":
        flash(f"{product.name} has history — deactivated, not deleted.", "info")
    else:
        flash(f"{product.name} deleted.", "info")
    return redirect(url_for("stock.index"))


# --- stock movements -------------------------------------------------

@bp.route("/products/<int:product_id>/adjust", methods=["POST"])
@login_required
@permission_required("stock.adjust")
def adjust_stock(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    f = request.form
    try:
        inv.apply_stock_movement(
            product=product,
            movement_type=f.get("movement_type", ""),
            quantity_milli=_qty_to_milli(f.get("quantity")),
            reason=f.get("reason", ""),
            user_id=current_user.id,
        )
        flash("Stock updated.", "info")
    except inv.InventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("stock.product_detail", product_id=product_id))


# --- barcodes -------------------------------------------------------

@bp.route("/products/<int:product_id>/barcodes", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def add_barcode(product_id: int):
    product = inv.get_product(product_id) or abort(404)
    f = request.form
    override = _rupees_to_paisa(f.get("price_override"))
    if override is not None:
        if not role_has_permission(current_user.role, "product.edit_price"):
            abort(403)
        require_step_up()
    try:
        if f.get("mode") == "generate":
            row = inv.generate_barcode(product=product, user_id=current_user.id)
        else:
            row = inv.assign_barcode(
                product=product,
                code=f.get("barcode", ""),
                user_id=current_user.id,
                price_override_paisa=override,
                label=f.get("label") or None,
            )
        flash(f"Barcode {row.barcode} added.", "info")
    except inv.InventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("stock.product_detail", product_id=product_id))


@bp.route("/barcodes/<int:barcode_id>/deactivate", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def deactivate_barcode(barcode_id: int):
    row = db.session.get(ProductBarcode, barcode_id) or abort(404)
    product_id = row.product_id
    inv.deactivate_barcode(row)
    flash("Barcode deactivated.", "info")
    return redirect(url_for("stock.product_detail", product_id=product_id))


@bp.route("/labels.pdf", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def label_sheet():
    specs: list[labels.LabelSpec] = []
    for raw in request.form.getlist("barcode_id"):
        row = db.session.get(ProductBarcode, _int_or_none(raw) or -1)
        if row is None:
            continue
        product = db.session.get(Product, row.product_id)
        price = row.price_override_paisa or product.sell_price_paisa
        caption = f"{product.name}  •  Rs {price // 100}"
        copies = max(1, _int_or_none(request.form.get(f"copies_{row.id}")) or 1)
        specs.extend([labels.LabelSpec(code=row.barcode, caption=caption)] * copies)

    if not specs:
        abort(400, description="No barcodes selected.")

    pdf = labels.render_label_sheet(specs, geometry=labels.load_geometry())
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="sukoon-labels.pdf",
    )


# --- categories ---------------------------------------------------

@bp.route("/categories", methods=["GET", "POST"])
@login_required
@permission_required("catalog.manage")
def categories():
    if request.method == "POST":
        try:
            inv.create_category(
                request.form.get("name", ""),
                display_order=_int_or_none(request.form.get("display_order")) or 0,
            )
            flash("Category added.", "info")
        except inv.InventoryError as exc:
            flash(str(exc), "error")
        return redirect(url_for("stock.categories"))
    return render_template(
        "stock/categories.html", categories=inv.list_categories(include_inactive=True)
    )


@bp.route("/categories/<int:category_id>", methods=["POST"])
@login_required
@permission_required("catalog.manage")
def update_category(category_id: int):
    category = db.session.get(Category, category_id) or abort(404)
    # The checkbox only submits when ticked; a hidden marker tells us it was on
    # the form at all, so an edit that doesn't touch it doesn't deactivate.
    is_active = None
    if request.form.get("active_field_present"):
        is_active = request.form.get("is_active") == "on"
    try:
        inv.update_category(
            category,
            name=request.form.get("name") or None,
            display_order=_int_or_none(request.form.get("display_order")),
            is_active=is_active,
        )
        flash("Category saved.", "info")
    except inv.InventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("stock.categories"))
