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
