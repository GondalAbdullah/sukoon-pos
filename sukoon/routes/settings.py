"""The shop's settings: the receipt printer, the address the other tills use, and the backups.

Everything here was previously only reachable by editing the database by hand, which a shop owner
cannot do. The network address is the one ADR-0038 §10 promised the tills would be pointed at.
"""
from __future__ import annotations

import socket
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
from flask_login import login_required

from sukoon.extensions import db
from sukoon.offsite import OffsiteError
from sukoon.routes.guards import permission_required
from sukoon.services import backup_status, clock, offsite_service, settings_service
from sukoon.services.notifications import secret_store
from sukoon.services.receipts import printer
from sukoon.services.receipts.receipt import render_test_escpos

bp = Blueprint("settings", __name__, url_prefix="/settings")

PRINTER_KINDS = [
    ("none", "No printer — receipts as PDF only"),
    ("windows", "A printer installed in Windows (recommended for USB printers)"),
    ("network", "A printer with its own network address"),
]


def lan_address() -> str | None:
    """The address the other tills should use. Asking the operating system which address it would
    use to reach the network is more reliable than the machine's name."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("192.0.2.1", 80))  # reserved, documentation-only: nothing is sent
            return probe.getsockname()[0]
    except OSError:
        return None


def _page(status: int = 200):
    from sukoon.services.receipts import windows_printer

    port = current_app.config.get("SUKOON_PORT", 5000)
    address = lan_address()
    return render_template(
        "settings/index.html",
        kinds=PRINTER_KINDS,
        kind=printer.printer_kind(),
        windows_name=printer.windows_printer_name(),
        windows_printers=windows_printer.list_printers(),
        on_windows=windows_printer.available(),
        host=settings_service.get("receipt.printer.host", ""),
        port_number=settings_service.get("receipt.printer.port", "9100"),
        till_address=f"http://{address}:{port}" if address else None,
        data_dir=current_app.config.get("DATA_DIR"),
        backup=backup_status.describe(current_app.config.get("BACKUP_DIR")),
        offsite=offsite_service.describe(current_app.config.get("BACKUP_DIR"),
                                         current_app.config.get("OFFSITE_SECRET_PATH")),
        offsite_form={
            "endpoint": settings_service.get(offsite_service.ENDPOINT, ""),
            "bucket": settings_service.get(offsite_service.BUCKET, ""),
            "access_key_id": settings_service.get(offsite_service.ACCESS_KEY_ID, ""),
        },
    ), status


@bp.route("/")
@login_required
@permission_required("settings.manage")
def index():
    return _page()


@bp.route("/printer", methods=["POST"])
@login_required
@permission_required("settings.manage")
def save_printer():
    # Everything is checked before anything is written. Writing the kind first left Sukoon set to
    # "a Windows printer" with no printer chosen when the form was rejected — and every sale would
    # then fail to print.
    kind = request.form.get("kind", "none")
    name = request.form.get("windows_name", "").strip()
    host = request.form.get("host", "").strip()
    if kind not in {code for code, _ in PRINTER_KINDS}:
        flash("Choose how the receipt printer is connected.", "error")
        return _page(400)
    if kind == "windows" and not name:
        flash("Choose which Windows printer to print receipts on.", "error")
        return _page(400)
    if kind == "network" and not host:
        flash("Type the printer's network address.", "error")
        return _page(400)

    settings_service.set("receipt.printer.kind", kind)
    if kind == "windows":
        settings_service.set("receipt.printer.windows_name", name)
    if kind == "network":
        settings_service.set("receipt.printer.host", host)
        settings_service.set("receipt.printer.port", request.form.get("port", "9100").strip())
    from sukoon.extensions import db

    db.session.commit()
    flash("Printer settings saved. Print a test receipt to check them.", "info")
    return redirect(url_for("settings.index"))


@bp.route("/printer/test", methods=["POST"])
@login_required
@permission_required("settings.manage")
def test_print():
    try:
        shop_name = settings_service.get("shop.name", "Al-Rehman General Store")
        when = clock.format_clock(datetime.now(UTC), with_date=True)
        printer.send(render_test_escpos(shop_name, when))
    except printer.PrinterUnavailable as exc:
        current_app.logger.warning("test print failed: %s", exc)
        flash(f"The printer didn't take it: {exc}", "error")
        return _page(200)
    flash("Sent. If nothing came out, the printer is chosen but not reachable.", "info")
    return redirect(url_for("settings.index"))


# --- offsite backup (ADR-0037) ------------------------------------------------------------------

def _offsite_paths():
    return (current_app.config.get("BACKUP_DIR"),
            current_app.config.get("OFFSITE_SECRET_PATH"),
            current_app.config.get("BACKUP_KEY_PATH"))


@bp.route("/offsite", methods=["POST"])
@login_required
@permission_required("settings.manage")
def save_offsite():
    """The Admin types what Cloudflare (or any S3 service) gave them. The secret access key goes
    where the WhatsApp key goes — encrypted by Windows, never in the database or a backup."""
    backups_dir, secret_path, key_path = _offsite_paths()
    endpoint = request.form.get("endpoint", "").strip().rstrip("/")
    bucket = request.form.get("bucket", "").strip()
    access_key_id = request.form.get("access_key_id", "").strip()
    secret = request.form.get("secret_access_key", "").strip()

    if not (endpoint.startswith("https://") and bucket and access_key_id):
        flash("Fill in the address (https://…), the bucket name and the access key ID.", "error")
        return _page(400)
    if not secret and not (secret_path and secret_store.has_key(secret_path)):
        flash("Paste the secret access key — it is only shown once by Cloudflare.", "error")
        return _page(400)

    settings_service.set(offsite_service.ENDPOINT, endpoint)
    settings_service.set(offsite_service.BUCKET, bucket)
    settings_service.set(offsite_service.ACCESS_KEY_ID, access_key_id)
    if secret:
        secret_store.save_key(secret_path, secret)
    offsite_service.encryption_key(key_path, create=True)   # made once, then never changed
    settings_service.set(offsite_service.ENABLED, "1")
    db.session.commit()
    flash("Offsite backup set up. Send one now to prove it works.", "info")
    return redirect(url_for("settings.index"))


@bp.route("/offsite/send", methods=["POST"])
@login_required
@permission_required("settings.manage")
def send_offsite():
    backups_dir, secret_path, key_path = _offsite_paths()
    try:
        name = offsite_service.send_latest(backups_dir=backups_dir, secret_path=secret_path,
                                           key_path=key_path)
    except (offsite_service.NotConfigured, OffsiteError) as exc:
        offsite_service.record(backups_dir, datetime.now(UTC), ok=False, error=str(exc))
        flash(f"Offsite backup failed: {exc}", "error")
        return _page(200)
    flash(f"Sent {name}." if name else "Everything is already offsite.", "info")
    return redirect(url_for("settings.index"))


@bp.route("/offsite/check", methods=["POST"])
@login_required
@permission_required("settings.manage")
def check_offsite():
    """Bring the newest offsite backup back, unlock it and open it — the proof (ADR-0037 §6)."""
    backups_dir, secret_path, key_path = _offsite_paths()
    try:
        name, sales = offsite_service.check(backups_dir=backups_dir, secret_path=secret_path,
                                            key_path=key_path)
    except (offsite_service.NotConfigured, OffsiteError) as exc:
        offsite_service.record(backups_dir, datetime.now(UTC), ok=False, error=str(exc))
        flash(f"The offsite backup could not be checked: {exc}", "error")
        return _page(200)
    flash(f"{name} came back, unlocked and readable — {sales} sales in it.", "info")
    return redirect(url_for("settings.index"))


@bp.route("/offsite/recovery-sheet")
@login_required
@permission_required("settings.manage")
def recovery_sheet():
    """The key, printed. Without it every offsite backup is unreadable (ADR-0037 §5)."""
    _, _, key_path = _offsite_paths()
    try:
        key_text = offsite_service.recovery_sheet_key(key_path)
    except offsite_service.NotConfigured:
        flash("Set up offsite backup first — the key is made then.", "error")
        return _page(400)
    return render_template("settings/recovery_sheet.html", key_text=key_text,
                           shop_name=settings_service.get("shop.name", "the shop"),
                           made_at=clock.format_shop_time(datetime.now(UTC)))
