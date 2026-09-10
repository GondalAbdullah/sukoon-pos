"""The Till — cart, payment, invoice, Sale Complete (Development Specification
Phase 3).

Thin by construction (ADR-0003 §2): this module marshals the session cart to and
from ``sales_service`` and renders. Every line total, the subtotal, the invoice
number, the stock deduction and the ledger entry are decided in
``sales_service`` / ``pricing``, never here.

The cart lives in the signed session for v1. A sealed-pack line carries a
stepper quantity; a loose line (``allows_fractional``) is added with **no**
quantity and sits in a 'needs weight' state until the cashier types a weight or a
rupee amount (ADR-0005, context.md §4b). Checkout is blocked while any line is
unweighed.
"""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from sukoon.extensions import db
from sukoon.models import Product, Sale
from sukoon.routes.guards import permission_required
from sukoon.services import inventory_service as inv
from sukoon.services import pricing, sales_service
from sukoon.services.auth_service import role_has_permission
from sukoon.services.sales_service import CartLine

bp = Blueprint("till", __name__, url_prefix="/till")

_CART_KEY = "cart"


# --- session cart plumbing ------------------------------------------------


def _cart() -> list[dict]:
    return session.get(_CART_KEY, [])


def _save(cart: list[dict]) -> None:
    session[_CART_KEY] = cart
    session.modified = True


def _rupees_to_paisa(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return round(float(raw) * 100)
    except ValueError:
        return None


def _weight_to_milli(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return round(float(raw) * 1000)
    except ValueError:
        return None


def _to_cartline(row: dict) -> CartLine | None:
    product = db.session.get(Product, row["product_id"])
    if product is None or not product.is_active:
        return None
    return CartLine(
        product=product,
        quantity_milli=row["quantity_milli"],
        unit_price_paisa=row["unit_price_paisa"],
        quantity_source=row["quantity_source"],
        typed_amount_paisa=row.get("typed_amount_paisa"),
        product_barcode_id=row.get("product_barcode_id"),
    )


def _resolve(code: str) -> tuple[Product, int, int | None] | None:
    """A scanned code or a typed fragment -> (product, unit_price, barcode_id).
    Barcode first (ADR-0009 resolver), then a unique name/SKU match."""
    match = inv.resolve_barcode(code)
    if match is not None:
        return match.product, match.unit_price_paisa, match.product_barcode.id
    rows, total = inv.list_products(query=code, limit=2)
    if total == 1:
        return rows[0], rows[0].sell_price_paisa, None
    return None


# --- the till screen ----------------------------------------------------


@bp.route("/")
@login_required
@permission_required("sale.ring")
def index():
    lines: list[CartLine] = []
    kept: list[dict] = []
    for row in _cart():
        line = _to_cartline(row)
        if line is None:
            flash("An item left the catalogue and was removed from the cart.", "error")
            continue
        kept.append(row)
        lines.append(line)
    if len(kept) != len(_cart()):
        _save(kept)

    summary = sales_service.summarize_cart(lines)
    return render_template(
        "till/till.html",
        rows=kept,
        lines=lines,
        summary=summary,
        line_totals=summary.line_totals_paisa,
        new_code=request.args.get("new") or None,
        can_create_provisional=role_has_permission(
            current_user.role, "product.create_provisional"
        ),
    )


@bp.route("/add", methods=["POST"])
@login_required
@permission_required("sale.ring")
def add():
    code = (request.form.get("code") or "").strip()
    product_id = request.form.get("product_id")

    resolved = None
    if product_id:
        product = db.session.get(Product, int(product_id))
        if product is not None:
            resolved = (product, product.sell_price_paisa, None)
    elif code:
        resolved = _resolve(code)

    if resolved is None:
        # Scan-as-you-go (ADR-0011 §2): an unknown code is not a dead end — offer
        # to create it as a provisional product, if the cashier may.
        if code and role_has_permission(
            current_user.role, "product.create_provisional"
        ):
            return redirect(url_for("till.index", new=code))
        flash(f"Nothing matched “{code}”.", "error")
        return redirect(url_for("till.index"))

    product, unit_price, barcode_id = resolved
    _add_to_cart(product, unit_price, barcode_id)
    return redirect(url_for("till.index"))


def _add_to_cart(product: Product, unit_price: int, barcode_id: int | None) -> None:
    cart = _cart()
    if not product.allows_fractional:
        # sealed pack: one row per product, bump the stepper if already there
        for row in cart:
            if row["product_id"] == product.id and row["quantity_source"] == "stepper":
                row["quantity_milli"] += 1000
                _save(cart)
                return
    cart.append(
        {
            "product_id": product.id,
            "name": product.name,
            "unit_label": product.unit_label,
            "unit_price_paisa": unit_price,
            "allows_fractional": product.allows_fractional,
            # sealed -> a stepper of 1; loose -> waiting for a weight (ADR-0005)
            "quantity_milli": None if product.allows_fractional else 1000,
            "quantity_source": "manual_weight" if product.allows_fractional else "stepper",
            "typed_amount_paisa": None,
            "product_barcode_id": barcode_id,
        }
    )
    _save(cart)


@bp.route("/new", methods=["POST"])
@login_required
@permission_required("product.create_provisional")
def new_provisional():
    """Create a bare product mid-sale and drop it in the cart (ADR-0011 §2 /
    O-16). Name and price only, so it is always provisional (ADR-0012); it lands
    in 'Needs completing' for an Admin to finish later."""
    f = request.form
    code = (f.get("code") or "").strip()
    try:
        product = inv.create_product(
            name=f.get("name", ""),
            sell_price_paisa=_rupees_to_paisa(f.get("sell_price")),
            created_by_user_id=current_user.id,
        )
        barcode_id = None
        if code:
            row = inv.assign_barcode(product=product, code=code, user_id=current_user.id)
            barcode_id = row.id
    except inv.InventoryError as exc:
        flash(str(exc), "error")
        return redirect(url_for("till.index", new=code))

    _add_to_cart(product, product.sell_price_paisa, barcode_id)
    flash(f"{product.name} added ({product.sku}) — needs completing later.", "info")
    return redirect(url_for("till.index"))


@bp.route("/line/<int:index>", methods=["POST"])
@login_required
@permission_required("sale.ring")
def update_line(index: int):
    cart = _cart()
    if not 0 <= index < len(cart):
        abort(404)
    row = cart[index]
    op = request.form.get("op")

    if op == "remove":
        cart.pop(index)
        _save(cart)
        return redirect(url_for("till.index"))

    if op in {"inc", "dec"}:
        if row["quantity_source"] != "stepper":
            abort(400)
        row["quantity_milli"] += 1000 if op == "inc" else -1000
        if row["quantity_milli"] <= 0:
            cart.pop(index)
        _save(cart)
        return redirect(url_for("till.index"))

    if op == "set_weight":
        milli = _weight_to_milli(request.form.get("weight"))
        if not milli or milli <= 0:
            flash("Enter a weight.", "error")
            return redirect(url_for("till.index"))
        row["quantity_source"] = "manual_weight"
        row["quantity_milli"] = milli
        row["typed_amount_paisa"] = None
        _save(cart)
        return redirect(url_for("till.index"))

    if op == "set_amount":
        amount = _rupees_to_paisa(request.form.get("amount"))
        if not amount or amount <= 0:
            flash("Enter an amount in whole rupees.", "error")
            return redirect(url_for("till.index"))
        try:
            milli = pricing.compute_quantity_from_amount(
                amount, row["unit_price_paisa"]
            )
        except ValueError:
            flash("That item has no price to work from.", "error")
            return redirect(url_for("till.index"))
        row["quantity_source"] = "manual_amount"
        row["typed_amount_paisa"] = amount
        row["quantity_milli"] = milli
        _save(cart)
        return redirect(url_for("till.index"))

    abort(400)


@bp.route("/clear", methods=["POST"])
@login_required
@permission_required("sale.ring")
def clear():
    session.pop(_CART_KEY, None)
    return redirect(url_for("till.index"))


# --- checkout ---------------------------------------------------------


@bp.route("/checkout", methods=["POST"])
@login_required
@permission_required("sale.take_payment")
def checkout():
    lines: list[CartLine] = []
    for row in _cart():
        line = _to_cartline(row)
        if line is None:
            flash("An item left the catalogue. Check the cart and try again.", "error")
            return redirect(url_for("till.index"))
        lines.append(line)

    summary = sales_service.summarize_cart(lines)
    if not lines:
        flash("The cart is empty.", "error")
        return redirect(url_for("till.index"))
    if not summary.ready:
        flash("Every loose item still needs a weight.", "error")
        return redirect(url_for("till.index"))

    payment_method = request.form.get("payment_method", "")
    tendered = _rupees_to_paisa(request.form.get("amount_tendered"))
    customer_id = request.form.get("customer_id")

    try:
        sale = sales_service.record_sale(
            lines=lines,
            payment_method=payment_method,
            user_id=current_user.id,
            customer_id=int(customer_id) if customer_id else None,
            amount_tendered_paisa=tendered,
        )
    except (sales_service.SaleError, inv.InventoryError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("till.index"))

    session.pop(_CART_KEY, None)
    return redirect(url_for("till.complete", sale_id=sale.id))


@bp.route("/complete/<int:sale_id>")
@login_required
@permission_required("sale.ring")
def complete(sale_id: int):
    sale = db.session.get(Sale, sale_id) or abort(404)
    items = list(sale.items)
    return render_template("till/complete.html", sale=sale, items=items)
