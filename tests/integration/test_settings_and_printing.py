"""The Settings screen and printing through Windows (ADR-0038 §10, ADR-0039).

Until now the printer could only be configured by editing the database by hand, so an installed
Sukoon never printed at all — found by the developer the day before go-live.

The Windows path itself is exercised against the real spooler only on Windows; here the seam is:
the right printer name, every failure turned into ``PrinterUnavailable`` so a sale still completes.
"""
from __future__ import annotations

import pytest

from sukoon.services import settings_service
from sukoon.services.receipts import printer, windows_printer
from sukoon.services.receipts.receipt import render_test_escpos
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

# --- the screen ------------------------------------------------------------------------------

def test_a_cashier_cannot_see_or_change_settings(client, seeded, login):
    login("T1", CASHIER_PASSWORD)
    assert client.get("/settings/").status_code == 403
    assert client.post("/settings/printer", data={"kind": "none"}).status_code == 403


def test_the_settings_screen_shows_the_address_the_other_tills_use(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    page = client.get("/settings/")
    assert page.status_code == 200
    assert b"The other tills" in page.data
    from sukoon.routes.settings import lan_address

    address = lan_address()
    if address:  # a machine with no network at all has nothing to show
        assert address.encode() in page.data


def test_choosing_a_windows_printer_is_remembered(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    response = client.post("/settings/printer",
                           data={"kind": "windows", "windows_name": "XP-80C"},
                           follow_redirects=True)
    assert response.status_code == 200
    assert printer.printer_kind() == "windows" and printer.windows_printer_name() == "XP-80C"


def test_a_windows_printer_with_no_name_chosen_is_refused(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    response = client.post("/settings/printer", data={"kind": "windows", "windows_name": ""})
    assert response.status_code == 400 and b"which Windows printer" in response.data
    assert printer.printer_kind() == "none"


def test_a_network_printer_keeps_its_address_and_port(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    client.post("/settings/printer",
                data={"kind": "network", "host": "192.168.1.50", "port": "9100"})
    assert settings_service.get("receipt.printer.host") == "192.168.1.50"
    assert settings_service.get("receipt.printer.port") == "9100"


def test_a_failed_test_print_explains_itself_instead_of_erroring(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    response = client.post("/settings/printer/test", follow_redirects=True)
    assert response.status_code == 200          # no printer configured
    assert b"didn&#39;t take it" in response.data
    assert b"No receipt printer is configured" in response.data


# --- the Windows seam -------------------------------------------------------------------------

def test_the_test_slip_is_escpos_bytes_naming_the_shop():
    data = render_test_escpos("Al-Rehman General Store", "18 Sep 2026, 9:20 AM")
    assert b"Al-Rehman General Store" in data and b"Test receipt" in data
    assert data.startswith(b"\x1b")             # an ESC/POS command stream


def test_printing_goes_to_the_chosen_windows_printer(app, monkeypatch):
    sent = {}
    monkeypatch.setattr(windows_printer, "send_raw",
                        lambda name, data, **kw: sent.update(name=name, data=data))
    settings_service.set("receipt.printer.kind", "windows")
    settings_service.set("receipt.printer.windows_name", "XP-80C")
    printer.send(b"\x1b@hello")
    assert sent == {"name": "XP-80C", "data": b"\x1b@hello"}


def test_a_windows_printer_that_fails_never_breaks_a_sale(app, monkeypatch):
    def refuse(name, data, **kw):
        raise windows_printer.WindowsPrintError("Windows could not open the printer (error 1801)")

    monkeypatch.setattr(windows_printer, "send_raw", refuse)
    settings_service.set("receipt.printer.kind", "windows")
    settings_service.set("receipt.printer.windows_name", "Gone")
    with pytest.raises(printer.PrinterUnavailable, match="1801"):
        printer.send(b"x")


def test_no_printer_chosen_says_so(app):
    settings_service.set("receipt.printer.kind", "windows")
    settings_service.set("receipt.printer.windows_name", "")
    with pytest.raises(printer.PrinterUnavailable, match="Settings screen"):
        printer.send(b"x")


def test_off_windows_there_is_nothing_to_list_and_printing_refuses_clearly():
    import sys

    if sys.platform == "win32":
        pytest.skip("checks the behaviour off Windows")
    assert windows_printer.available() is False
    assert windows_printer.list_printers() == []
    with pytest.raises(windows_printer.WindowsPrintError, match="only works on Windows"):
        windows_printer.send_raw("XP-80C", b"x")


# --- the backup key, when this PC can no longer read it (ADR-0037 §5) --------------------------

def _offsite_ready(app, tmp_path):
    from sukoon.services import offsite_service

    app.config.update(BACKUP_DIR=str(tmp_path), OFFSITE_SECRET_PATH=str(tmp_path / "offsite.key"),
                      BACKUP_KEY_PATH=str(tmp_path / "backup.key"))
    settings_service.set(offsite_service.ENDPOINT, "https://storage.example")
    settings_service.set(offsite_service.BUCKET, "books")
    settings_service.set(offsite_service.ACCESS_KEY_ID, "id")
    return offsite_service


def test_an_unreadable_backup_key_explains_itself_instead_of_erroring(client, seeded, login,
                                                                      app, tmp_path, monkeypatch):
    offsite_service = _offsite_ready(app, tmp_path)
    offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"], create=True)
    from sukoon.services.notifications import secret_store

    def refuse(*args, **kwargs):
        raise secret_store.KeyStoreError("Windows could not protect or unprotect the key.")

    monkeypatch.setattr(secret_store, "load_key", refuse)
    login("Owner", ADMIN_PASSWORD)

    for path in ("/settings/offsite/send", "/settings/offsite/check"):
        response = client.post(path, follow_redirects=True)
        assert response.status_code == 200, path          # not a 500 page
        assert b"recovery sheet" in response.data, path

    # the sheet cannot be printed from a key this PC can't read — it says so, rather than 500ing
    sheet = client.get("/settings/offsite/recovery-sheet", follow_redirects=True)
    assert sheet.status_code == 400 and b"recovery sheet" in sheet.data


def test_the_key_from_the_recovery_sheet_can_be_typed_back_in(client, seeded, login, app, tmp_path):
    offsite_service = _offsite_ready(app, tmp_path)
    original = offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"], create=True)
    printed = offsite_service.recovery_sheet_key(app.config["BACKUP_KEY_PATH"])
    (tmp_path / "backup.key").unlink()

    login("Owner", ADMIN_PASSWORD)
    response = client.post("/settings/offsite/key", data={"recovery_key": printed},
                           follow_redirects=True)
    assert response.status_code == 200 and b"in place" in response.data
    assert offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"]) == original


def test_a_mistyped_recovery_key_is_refused(client, seeded, login, app, tmp_path):
    _offsite_ready(app, tmp_path)
    login("Owner", ADMIN_PASSWORD)
    # "obviously wrong" is, by accident, valid base64 — so Sukoon complains about its length
    short = client.post("/settings/offsite/key", data={"recovery_key": "obviously wrong"})
    assert short.status_code == 400 and b"32 bytes" in short.data
    # characters outside the alphabet are the other kind of typo
    garbled = client.post("/settings/offsite/key", data={"recovery_key": "not-a-key!! @@"})
    assert garbled.status_code == 400 and b"doesn&#39;t look like" in garbled.data


def test_starting_a_new_key_needs_the_admins_own_password(client, seeded, login, app, tmp_path):
    offsite_service = _offsite_ready(app, tmp_path)
    original = offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"], create=True)
    login("Owner", ADMIN_PASSWORD)

    refused = client.post("/settings/offsite/key", data={"action": "new"})
    assert refused.status_code == 403
    assert offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"]) == original

    allowed = client.post("/settings/offsite/key",
                          data={"action": "new", "step_up_password": ADMIN_PASSWORD},
                          follow_redirects=True)
    assert allowed.status_code == 200
    assert offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"]) != original


# --- receipt width (80 mm paper, 2026-10-28) ------------------------------------------------

def test_the_receipt_width_is_chosen_on_the_printer_form(client, seeded, login):
    from sukoon.services.receipts.receipt import receipt_width

    login("Owner", ADMIN_PASSWORD)
    page = client.get("/settings/").get_data(as_text=True)
    assert 'name="chars_per_line"' in page and "48 characters a line" in page
    assert receipt_width() == 48  # 80 mm by default
    client.post("/settings/printer", data={"kind": "none", "chars_per_line": "42"})
    assert receipt_width() == 42
    resp = client.post("/settings/printer", data={"kind": "none", "chars_per_line": "99"})
    assert resp.status_code == 400 and receipt_width() == 42


def test_a_form_without_the_width_keeps_80mm(client, seeded, login):
    """An older page posting without the field must not fail the save."""
    from sukoon.services.receipts.receipt import receipt_width

    login("Owner", ADMIN_PASSWORD)
    client.post("/settings/printer", data={"kind": "none"})
    assert receipt_width() == 48


# --- shop details (ADR-0046 §3) ---------------------------------------------------------------

def test_shop_details_are_saved_and_shown(client, seeded, login):
    from sukoon.services import shop_profile

    login("Owner", ADMIN_PASSWORD)
    resp = client.post("/settings/shop", data={"shop_name": "  Nizami   Store ",
                                               "shop_address": "Main Bazaar, Johar Town, Lahore",
                                               "shop_phone": "0300 1234567"},
                       follow_redirects=True)
    assert "Shop details saved." in resp.get_data(as_text=True)
    shop = shop_profile.get()
    assert (shop.name, shop.address, shop.phone) == (
        "Nizami Store", "Main Bazaar, Johar Town, Lahore", "0300 1234567")
    page = client.get("/settings/").get_data(as_text=True)
    assert 'value="Main Bazaar, Johar Town, Lahore"' in page


def test_a_shop_needs_a_name(client, seeded, login):
    from sukoon.services import shop_profile

    login("Owner", ADMIN_PASSWORD)
    resp = client.post("/settings/shop", data={"shop_name": "  ", "shop_address": "x"})
    assert resp.status_code == 400 and "needs a name" in resp.get_data(as_text=True)
    assert shop_profile.get().address is None


def test_a_cashier_cannot_change_shop_details(client, seeded, login):
    login("T1", CASHIER_PASSWORD)
    assert client.post("/settings/shop", data={"shop_name": "X"}).status_code == 403
