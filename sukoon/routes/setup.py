"""The one-time setup screen (ADR-0038 §6). Thin: the rules live in ``setup_service``.

What the route adds is where the request came from, which a service can't know:

* **The shop PC only.** Until the first account exists, anyone who can reach Sukoon could
  create its owner. Sukoon listens on the shop's network (ADR-0038 §10), so setup is accepted
  only from the PC itself — the desktop window, or a browser on that machine. A till elsewhere
  is told to finish setup on the shop PC.
* **Same-origin posts only.** A page from another site, opened in a browser on the shop PC
  during that window, must not be able to submit the form.
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
from flask_login import login_user

from sukoon.services import setup_service

bp = Blueprint("setup", __name__)

_LOCAL_ADDRESSES = {"127.0.0.1", "::1"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_DONE = "sukoon.setup_done"
_OPEN_ENDPOINTS = {"setup.setup", "static"}


def _from_this_pc() -> bool:
    """The connection comes from this machine *and* was addressed to it by a local name.
    The second half defeats DNS rebinding: a hostile domain made to resolve to 127.0.0.1
    arrives from a local address, but carries its own name in the Host header."""
    host = request.host.rsplit(":", 1)[0] if not request.host.startswith("[") \
        else request.host.split("]")[0] + "]"
    return request.remote_addr in _LOCAL_ADDRESSES and host.lower() in _LOCAL_HOSTS


def _same_origin() -> bool:
    origin = request.headers.get("Origin")
    return origin is None or origin.rstrip("/") == request.host_url.rstrip("/")


@bp.before_app_request
def _send_to_setup_until_done():
    """Every page leads to setup while there are no accounts. Once one exists it never goes
    back, so the answer is remembered and the database isn't asked on every request."""
    if current_app.extensions.get(_DONE) or request.endpoint in _OPEN_ENDPOINTS \
            or request.endpoint is None:
        return None
    if setup_service.needs_setup():
        return redirect(url_for("setup.setup"))
    current_app.extensions[_DONE] = True
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if not setup_service.needs_setup():
        return redirect(url_for("auth.login"))
    if not _from_this_pc():
        current_app.logger.warning("setup refused: request from %s", request.remote_addr)
        return render_template("setup/setup.html", elsewhere=True), 403

    form = {"shop_name": "", "owner_name": ""}
    if request.method == "POST":
        if not _same_origin():
            current_app.logger.warning("setup refused: cross-origin post from %s",
                                       request.headers.get("Origin"))
            return render_template("setup/setup.html", elsewhere=False, form=form), 403
        form = {k: request.form.get(k, "") for k in form}
        try:
            user = setup_service.complete_setup(
                shop_name=form["shop_name"], owner_name=form["owner_name"],
                password=request.form.get("password", ""),
                confirm=request.form.get("confirm", ""),
                min_length=current_app.config["PASSWORD_MIN_LENGTH"])
        except setup_service.SetupError as exc:
            flash(str(exc), "error")
            return render_template("setup/setup.html", elsewhere=False, form=form), 400
        except setup_service.SetupAlreadyDone:
            flash("Sukoon has already been set up on this PC. Sign in instead.", "info")
            return redirect(url_for("auth.login"))
        current_app.extensions[_DONE] = True
        current_app.logger.info("setup complete: first admin user=%s", user.id)
        login_user(user)  # the landing page already says "Sukoon is ready" — no second toast
        return redirect(url_for("main.placeholder"))

    return render_template("setup/setup.html", elsewhere=False, form=form)
