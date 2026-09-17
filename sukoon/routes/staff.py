"""Staff accounts (ADR-0008, ADR-0017). Thin: every rule lives in ``staff_service``.

Adding an account, changing someone's password, or turning an account off, all ask the Admin for
their own password again (step-up, ADR-0008 §5) — an account is a key to the shop's money.
"""
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from sukoon.extensions import db
from sukoon.models.user import ROLE_ADMIN, ROLE_CASHIER, User
from sukoon.routes.guards import permission_required, require_step_up
from sukoon.services import staff_service

bp = Blueprint("staff", __name__, url_prefix="/staff")


def _page(status: int = 200):
    return render_template("staff/index.html", staff=staff_service.list_staff(),
                           roles=(ROLE_CASHIER, ROLE_ADMIN)), status


@bp.route("/")
@login_required
@permission_required("staff.manage")
def index():
    return _page()


@bp.route("/", methods=["POST"])
@login_required
@permission_required("staff.manage")
def add():
    require_step_up()
    try:
        user = staff_service.add_staff(
            name=request.form.get("name", ""), role=request.form.get("role", ""),
            password=request.form.get("password", ""), confirm=request.form.get("confirm", ""),
            min_length=current_app.config["PASSWORD_MIN_LENGTH"])
    except staff_service.StaffError as exc:
        flash(str(exc), "error")
        return _page(400)
    current_app.logger.info("staff added: user=%s role=%s by=%s", user.id, user.role,
                            current_user.get_id())
    flash(f"{user.name} can now sign in as {user.initials}.", "info")
    return redirect(url_for("staff.index"))


def _target(user_id: int) -> User:
    from flask import abort

    return db.session.get(User, user_id) or abort(404)


@bp.route("/<int:user_id>/password", methods=["POST"])
@login_required
@permission_required("staff.manage")
def set_password(user_id: int):
    require_step_up()
    user = _target(user_id)
    try:
        staff_service.set_password(user, password=request.form.get("password", ""),
                                   confirm=request.form.get("confirm", ""),
                                   min_length=current_app.config["PASSWORD_MIN_LENGTH"])
    except staff_service.StaffError as exc:
        flash(str(exc), "error")
        return _page(400)
    current_app.logger.info("staff password reset: user=%s by=%s", user.id, current_user.get_id())
    flash(f"{user.name}'s password is changed. Tell them the new one in person.", "info")
    return redirect(url_for("staff.index"))


@bp.route("/<int:user_id>/active", methods=["POST"])
@login_required
@permission_required("staff.manage")
def set_active(user_id: int):
    require_step_up()
    user = _target(user_id)
    wanted = request.form.get("active") == "1"
    try:
        staff_service.set_active(user, active=wanted)
    except staff_service.StaffError as exc:
        flash(str(exc), "error")
        return _page(400)
    current_app.logger.info("staff %s: user=%s by=%s", "activated" if wanted else "deactivated",
                            user.id, current_user.get_id())
    flash(f"{user.name} can {'now' if wanted else 'no longer'} sign in.", "info")
    return redirect(url_for("staff.index"))


@bp.route("/<int:user_id>/role", methods=["POST"])
@login_required
@permission_required("staff.manage")
def set_role(user_id: int):
    require_step_up()
    user = _target(user_id)
    try:
        staff_service.set_role(user, role=request.form.get("role", ""))
    except staff_service.StaffError as exc:
        flash(str(exc), "error")
        return _page(400)
    current_app.logger.info("staff role: user=%s -> %s by=%s", user.id, user.role,
                            current_user.get_id())
    flash(f"{user.name} is now {'an admin' if user.role == ROLE_ADMIN else 'a cashier'}.", "info")
    return redirect(url_for("staff.index"))
