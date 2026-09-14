"""Khata screens — customers, balances, payments, statements (Development Spec
Phase 4; ADR-0013, ADR-0014, ADR-0015, ADR-0026). Thin: every rule lives in
``khata_service`` / ``ledger`` / ``statements``.
"""
from __future__ import annotations

from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from sukoon.extensions import db
from sukoon.models import Customer, Payment, User
from sukoon.routes.guards import permission_required
from sukoon.services import khata_service as khata
from sukoon.services import ledger, statements
from sukoon.services.auth_service import role_has_permission

bp = Blueprint("khata", __name__, url_prefix="/khata")

TILL_CUSTOMER_KEY = "till_customer_id"  # shared with routes/till.py


def _rupees_to_paisa(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return round(float(raw.replace(",", "")) * 100)
    except ValueError:
        return None


def _active_customer(customer_id: int) -> Customer:
    c = db.session.get(Customer, customer_id)
    if c is None or not c.is_active:
        abort(404)
    return c


def _can(code: str) -> bool:
    return role_has_permission(current_user.role, code)


# --- list + detail -----------------------------------------------------------------

@bp.route("/")
@login_required
@permission_required("khata.view")
def index():
    filter_ = request.args.get("filter", "all")
    if filter_ not in khata.LIST_FILTERS:
        filter_ = "all"
    q = (request.args.get("q") or "").strip()
    rows, counts = khata.list_customers(query=q, filter_=filter_)

    selected = None
    wanted = request.args.get("c", type=int)
    if wanted is not None:
        c = db.session.get(Customer, wanted)
        if c is not None and c.is_active:
            selected = c
    if selected is None and rows:
        selected = rows[0].customer

    detail = _detail(selected) if selected else None
    return render_template("khata/index.html", rows=rows, counts=counts, filter_=filter_, q=q,
                           selected=selected, detail=detail,
                           can_create=_can("customer.create"),
                           can_pay=_can("khata.record_payment"),
                           can_manage=_can("customer.manage_credit"))


def _detail(customer: Customer) -> dict:
    entries = khata.entries_for(customer.id)
    whole = ledger.compute_statement(entries, None, None)
    now = datetime.now(UTC)
    payments = {p.id: p for p in db.session.scalars(
        db.select(Payment).where(Payment.customer_id == customer.id))}
    doc = statements.build_statement(customer, statements.period_for("all"), now=now)
    recent = list(zip(reversed(whole.rows), reversed(doc.lines), strict=True))[:25]
    verifier = (db.session.get(User, customer.phone_verified_by_user_id)
                if customer.phone_verified_by_user_id else None)
    room = (None if customer.credit_limit_paisa is None
            else customer.credit_limit_paisa - customer.balance_paisa)
    return {
        "balance": ledger.describe_balance(customer.balance_paisa),
        "overdue": ledger.compute_overdue_status(entries, customer.credit_terms_days, now),
        "purchased_paisa": whole.purchased_paisa,
        "paid_paisa": whole.paid_paisa,
        "refunded_paisa": whole.refunded_paisa,
        "recent": recent,
        "entry_count": len(entries),
        "payments": payments,
        "verifier": verifier,
        "limit_room_paisa": room,
        "reconciles": not whole.discrepancies and whole.closing_paisa == customer.balance_paisa,
    }


# --- opening + editing a Khata ---------------------------------------------------

@bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("customer.create")
def new():
    return_to = request.values.get("return")
    if request.method == "GET":
        return render_template("khata/customer_form.html", customer=None, form={},
                               duplicates=None, return_to=return_to,
                               default_limit=khata.default_credit_limit_paisa())
    f = request.form
    try:
        customer = khata.create_customer(
            name=f.get("name", ""), phone_raw=f.get("phone"), address=f.get("address"),
            notes=f.get("notes"), verified_method=f.get("verify") or None,
            confirm_duplicate=f.get("confirm_duplicate") == "1", user_id=current_user.id,
        )
    except khata.DuplicatePhoneError as exc:
        return render_template("khata/customer_form.html", customer=None, form=f,
                               duplicates=exc.existing, return_to=return_to,
                               default_limit=khata.default_credit_limit_paisa())
    except khata.CustomerValidationError as exc:
        flash(str(exc), "error")
        return render_template("khata/customer_form.html", customer=None, form=f,
                               duplicates=None, return_to=return_to,
                               default_limit=khata.default_credit_limit_paisa()), 400

    flash(f"Khata opened for {customer.name}.", "info")
    if return_to == "till":
        session[TILL_CUSTOMER_KEY] = customer.id
        return redirect(url_for("till.index"))
    return redirect(url_for("khata.index", c=customer.id))


@bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("customer.create")
def edit(customer_id: int):
    customer = _active_customer(customer_id)
    if request.method == "GET":
        return render_template("khata/customer_form.html", customer=customer, form={},
                               duplicates=None, return_to=None,
                               can_manage=_can("customer.manage_credit"))
    f = request.form
    try:
        khata.update_contact(customer, name=f.get("name", ""), phone_raw=f.get("phone"),
                             address=f.get("address"), notes=f.get("notes"),
                             confirm_duplicate=f.get("confirm_duplicate") == "1")
    except khata.DuplicatePhoneError as exc:
        return render_template("khata/customer_form.html", customer=customer, form=f,
                               duplicates=exc.existing, return_to=None,
                               can_manage=_can("customer.manage_credit"))
    except khata.CustomerValidationError as exc:
        flash(str(exc), "error")
        return render_template("khata/customer_form.html", customer=customer, form=f,
                               duplicates=None, return_to=None,
                               can_manage=_can("customer.manage_credit")), 400
    flash("Saved.", "info")
    return redirect(url_for("khata.index", c=customer.id))


@bp.route("/<int:customer_id>/verify", methods=["POST"])
@login_required
@permission_required("customer.create")
def verify(customer_id: int):
    customer = _active_customer(customer_id)
    try:
        khata.verify_phone(customer, method=request.form.get("verify", ""),
                           user_id=current_user.id)
        flash("Number confirmed.", "info")
    except khata.KhataError as exc:
        flash(str(exc), "error")
    return redirect(url_for("khata.index", c=customer.id))


@bp.route("/<int:customer_id>/credit", methods=["POST"])
@login_required
@permission_required("customer.manage_credit")
def credit(customer_id: int):
    customer = _active_customer(customer_id)
    f = request.form
    limit = None if f.get("no_limit") == "1" else _rupees_to_paisa(f.get("credit_limit"))
    if f.get("no_limit") != "1" and limit is None:
        flash("Enter a limit in rupees, or choose no limit.", "error")
        return redirect(url_for("khata.edit", customer_id=customer.id))
    raw_terms = (f.get("credit_terms_days") or "").strip()
    try:
        terms = int(raw_terms) if raw_terms else None
        khata.set_credit_terms(customer, credit_limit_paisa=limit, credit_terms_days=terms)
    except ValueError:
        flash("Credit terms are a number of days.", "error")
        return redirect(url_for("khata.edit", customer_id=customer.id))
    except khata.KhataError as exc:
        flash(str(exc), "error")
        return redirect(url_for("khata.edit", customer_id=customer.id))
    flash("Credit limit and terms saved.", "info")
    return redirect(url_for("khata.index", c=customer.id))


@bp.route("/<int:customer_id>/remove", methods=["POST"])
@login_required
@permission_required("customer.manage_credit")
def remove(customer_id: int):
    customer = _active_customer(customer_id)
    name = customer.name
    try:
        outcome = khata.remove_customer(customer)
    except khata.CustomerHasBalanceError as exc:
        flash(str(exc), "error")
        return redirect(url_for("khata.index", c=customer_id))
    if session.get(TILL_CUSTOMER_KEY) == customer_id:
        session.pop(TILL_CUSTOMER_KEY, None)
    flash(f"{name}'s Khata was archived — its history is kept." if outcome == "archived"
          else f"{name} was removed.", "info")
    return redirect(url_for("khata.index"))


# --- payments -----------------------------------------------------------------------

@bp.route("/<int:customer_id>/payment", methods=["GET", "POST"])
@login_required
@permission_required("khata.record_payment")
def payment(customer_id: int):
    customer = _active_customer(customer_id)
    balance = ledger.describe_balance(customer.balance_paisa)
    if request.method == "GET":
        return render_template("khata/payment.html", customer=customer, balance=balance,
                               form={}, excess_paisa=None, methods=khata.PAYMENT_METHODS)
    f = request.form
    try:
        khata.record_payment(
            customer_id=customer.id, amount_paisa=_rupees_to_paisa(f.get("amount")),
            method=f.get("method", ""), reference=f.get("reference"),
            received_by_user_id=current_user.id,
            allow_overpayment=f.get("allow_overpayment") == "1",
        )
    except khata.OverpaymentError as exc:
        return render_template("khata/payment.html", customer=customer, balance=balance,
                               form=f, excess_paisa=exc.excess_paisa,
                               methods=khata.PAYMENT_METHODS)
    except khata.KhataError as exc:
        flash(str(exc), "error")
        return render_template("khata/payment.html", customer=customer, balance=balance,
                               form=f, excess_paisa=None, methods=khata.PAYMENT_METHODS), 400
    db.session.refresh(customer)
    flash(f"Payment recorded. {customer.name}: {statements.balance_words(customer.balance_paisa)}.",
          "info")
    return redirect(url_for("khata.index", c=customer.id))


# --- statements -------------------------------------------------------------------

@bp.route("/<int:customer_id>/statement")
@login_required
@permission_required("khata.view")
def statement(customer_id: int):
    customer = db.session.get(Customer, customer_id) or abort(404)
    period = statements.period_for(request.args.get("period"))
    doc = statements.build_statement(customer, period)
    return render_template("khata/statement.html", customer=customer, doc=doc, period=period,
                           periods=statements.recent_periods())


@bp.route("/<int:customer_id>/statement.pdf")
@login_required
@permission_required("khata.view")
def statement_pdf(customer_id: int):
    customer = db.session.get(Customer, customer_id) or abort(404)
    period = statements.period_for(request.args.get("period"))
    pdf = statements.render_pdf(statements.build_statement(customer, period))
    resp = make_response(pdf)
    resp.mimetype = "application/pdf"
    safe = "".join(ch if ch.isalnum() else "-" for ch in customer.name).strip("-") or "customer"
    resp.headers["Content-Disposition"] = f'inline; filename="khata-{safe}-{period.key}.pdf"'
    return resp
