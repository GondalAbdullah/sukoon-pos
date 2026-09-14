"""The Admin Messages screen (ADR-0033 §5): the WhatsApp log, the switch, the key, the
reply-to number, the daily cap, Check now, and Send test. Thin — the rules live in
``services/notifications``."""
from __future__ import annotations

import sys

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from sukoon.extensions import db
from sukoon.jobs.scheduler import provider_for
from sukoon.models import Customer
from sukoon.routes.guards import permission_required
from sukoon.services import settings_service
from sukoon.services.notifications import queue, secret_store
from sukoon.services.notifications.providers.factory import PHONE_NUMBER_ID
from sukoon.services.phone import normalise_phone

bp = Blueprint("messages", __name__, url_prefix="/messages")

STATUS_TABS = ("all", "failed", "abandoned", "pending", "sent")


def _key_path() -> str:
    return current_app.config["WHATSAPP_KEY_PATH"]


@bp.route("/")
@login_required
@permission_required("whatsapp.manage")
def index():
    tab = request.args.get("status", "all")
    if tab not in STATUS_TABS:
        tab = "all"
    rows = queue.log_rows(None if tab == "all" else tab, limit=200)
    names = {c.id: c.name for c in db.session.scalars(
        db.select(Customer).where(Customer.id.in_({r.customer_id for r in rows if r.customer_id})))}
    return render_template(
        "messages/index.html", rows=rows, names=names, tab=tab, tabs=STATUS_TABS,
        enabled=queue.is_enabled(), pause=queue.paused(),
        key_set=secret_store.has_key(_key_path()), key_saved_at=secret_store.saved_at(_key_path()),
        reply_to=queue.reply_to_number() or "",
        phone_number_id=settings_service.get(PHONE_NUMBER_ID) or "",
        cap=queue.daily_cap(), sent_today=queue.sent_today(), month_count=queue.month_count(),
        labels=queue.TYPE_LABELS, stuck_reason=queue.STUCK_REASON,
        provider_kind=current_app.config["WHATSAPP_PROVIDER"],
        key_encrypted=sys.platform == "win32",
    )


@bp.route("/settings", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def save_settings():
    f = request.form
    reply_to = (f.get("reply_to") or "").strip()
    if reply_to and normalise_phone(reply_to) is None:
        flash("The reply-to number doesn't look like a phone number.", "error")
        return redirect(url_for("messages.index"))
    try:
        cap = int((f.get("daily_cap") or "").strip())
        if cap < 1:
            raise ValueError
    except ValueError:
        flash("The daily limit must be a whole number of at least 1.", "error")
        return redirect(url_for("messages.index"))
    if not reply_to and queue.is_enabled():
        flash("Sending is on, so the reply-to number can't be removed. Switch sending off first.",
              "error")
        return redirect(url_for("messages.index"))
    settings_service.set(queue.REPLY_TO, reply_to or None)
    settings_service.set(PHONE_NUMBER_ID, (f.get("phone_number_id") or "").strip() or None)
    settings_service.set(queue.DAILY_CAP, cap)
    db.session.commit()
    flash("Message settings saved.", "info")
    return redirect(url_for("messages.index"))


@bp.route("/key", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def save_key():
    try:
        secret_store.save_key(_key_path(), request.form.get("access_key", ""))
    except secret_store.KeyStoreError as exc:
        flash(str(exc), "error")
        return redirect(url_for("messages.index"))
    current_app.logger.info("WhatsApp access key replaced")  # never the key itself
    flash("Access key saved. It won't be shown again.", "info")
    return redirect(url_for("messages.index"))


@bp.route("/switch", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def switch():
    turn_on = request.form.get("on") == "1"
    try:
        abandoned = queue.set_enabled(turn_on, key_present=secret_store.has_key(_key_path()))
    except queue.NotReady as exc:
        flash(str(exc), "error")
        return redirect(url_for("messages.index"))
    if turn_on:
        flash("WhatsApp sending is on.", "info")
    else:
        flash("WhatsApp sending is off." + (f" {abandoned} waiting message"
              f"{'' if abandoned == 1 else 's'} cancelled." if abandoned else ""), "info")
    return redirect(url_for("messages.index"))


@bp.route("/check", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def check():
    if queue.check_now(provider_for(current_app)):
        flash("WhatsApp is reachable. Sending is not paused.", "info")
    else:
        pause = queue.paused()
        flash(f"Still paused: {pause.reason}" if pause else "Still paused.", "error")
    return redirect(url_for("messages.index"))


@bp.route("/test", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def send_test():
    result = queue.send_test(provider_for(current_app), request.form.get("number", ""))
    flash(result.message, "info" if result.ok else "error")
    return redirect(url_for("messages.index"))


@bp.route("/<int:row_id>/retry", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def retry(row_id: int):
    flash("Put back in the queue." if queue.retry_now(row_id) else "That message can't be retried.",
          "info")
    return redirect(url_for("messages.index", status=request.args.get("status")))


@bp.route("/<int:row_id>/again", methods=["POST"])
@login_required
@permission_required("whatsapp.manage")
def again(row_id: int):
    copy = queue.send_again(row_id)
    flash("Queued again." if copy else "That message can't be sent again.", "info")
    return redirect(url_for("messages.index", status=request.args.get("status")))
