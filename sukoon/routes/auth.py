"""Login / logout (ADR-0008 §1). The blueprint parses the form, calls
``auth_service``, and renders — no lockout arithmetic or hashing lives here
(ADR-0003 §2)."""
from __future__ import annotations

from datetime import UTC, datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from sukoon.extensions import db
from sukoon.services import auth_service

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.placeholder"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "")
        password = request.form.get("password", "")
        try:
            user = auth_service.authenticate(
                identifier,
                password,
                datetime.now(UTC),
                max_attempts=current_app.config["LOGIN_MAX_ATTEMPTS"],
                lockout_minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"],
            )
        except auth_service.AccountLockedError:
            db.session.commit()
            flash("Too many attempts. Try again shortly.", "error")
            return render_template("auth/login.html"), 429
        except auth_service.AuthError as exc:
            db.session.commit()  # persist any failed-attempt increment
            flash(str(exc), "error")
            return render_template("auth/login.html"), 401

        db.session.commit()
        login_user(user)
        current_app.logger.info("login ok user=%s", user.id)
        next_url = request.args.get("next")
        return redirect(next_url or url_for("main.placeholder"))

    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    current_app.logger.info("logout user=%s", current_user.get_id())
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("auth.login"))
