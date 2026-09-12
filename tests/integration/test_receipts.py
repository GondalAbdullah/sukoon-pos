"""Receipts — content, ESC/POS bytes, PDF fallback (Development Specification
Phase 3 step 5; required test: 'sale completes and produces a PDF receipt when
no printer responds')."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sukoon.extensions import db
from sukoon.models import User
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import sales_service, settings_service
from sukoon.services.auth_service import hash_password
from sukoon.services.receipts import printer
from sukoon.services.receipts import service as receipts
from sukoon.services.receipts.receipt import (
    _wrap_centered,
    build_receipt,
    receipt_body,
    render_escpos,
    render_pdf,
)
from sukoon.services.sales_service import CartLine
from tests.conftest import CASHIER_PASSWORD

JAN = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


@pytest.fixture
def cashier(app):
    u = User(name="Sana", initials="SN", role="cashier", password_hash=hash_password("x"))
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def sale(app, cashier):
    seed_invoice_counter()
    milk = inv.create_product(name="Milk 1L", sell_price_paisa=28_000)
    rice = inv.create_product(
        name="Rice loose", sell_price_paisa=16_000, allows_fractional=True, unit_label="kg"
    )
    for p in (milk, rice):
        inv.apply_stock_movement(
            product=p, movement_type="stock_in", quantity_milli=50_000,
            reason="in", user_id=cashier.id,
        )
    return sales_service.record_sale(
        lines=[
            CartLine(product=milk, quantity_milli=2_000, unit_price_paisa=28_000,
                     quantity_source="stepper"),
            CartLine(product=rice, quantity_milli=500, unit_price_paisa=16_000,
                     quantity_source="manual_weight"),
        ],
        payment_method="cash", user_id=cashier.id, amount_tendered_paisa=100_000,
        now=JAN,
    )


# --- content ---------------------------------------------------------

def test_build_receipt_pulls_the_sale_together(sale):
    data = build_receipt(sale)
    assert data.invoice_number == sale.invoice_number
    assert data.cashier_name == "Sana"
    assert data.shop_name == "Al-Rehman General Store"
    assert [line.name for line in data.lines] == ["Milk 1L", "Rice loose"]
    assert data.total_paisa == sale.total_paisa
    assert data.change_paisa == 100_000 - sale.total_paisa


def test_the_shop_name_and_contact_come_from_settings(sale):
    settings_service.set("shop.name", "Al-Rehman Kiryana")
    settings_service.set("shop.contact", "Gulberg, Lahore · 0300-1234567")
    db.session.commit()
    data = build_receipt(sale)
    assert data.shop_name == "Al-Rehman Kiryana"
    assert "0300-1234567" in data.shop_contact


def test_the_till_name_appears_when_the_sale_carries_one(cashier):
    # ADR-0023: terminal_label is None on sales rung before a till was named
    milk = inv.create_product(name="Milk 1L", sell_price_paisa=28_000)
    inv.apply_stock_movement(product=milk, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=cashier.id)
    named = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=cashier.id, now=JAN, terminal_label="Till 2",
    )
    unnamed = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=cashier.id, now=JAN,
    )
    assert "Till" in " ".join(receipt_body(build_receipt(named)))
    assert b"Till 2" in render_escpos(build_receipt(named))
    assert "Till" not in " ".join(receipt_body(build_receipt(unnamed)))


# --- ESC/POS --------------------------------------------------------

def test_escpos_bytes_carry_the_invoice_and_a_cut(sale):
    raw = render_escpos(build_receipt(sale))
    assert isinstance(raw, bytes)
    assert sale.invoice_number.encode() in raw
    assert b"Al-Rehman General Store" in raw
    assert b"\x1dV" in raw  # ESC/POS paper-cut command


# --- PDF -----------------------------------------------------------

def test_pdf_fallback_renders_a_pdf(sale):
    pdf = render_pdf(build_receipt(sale))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500


# --- word-wrap (a real bug, found by rendering and looking) --------

def test_short_text_does_not_wrap():
    assert _wrap_centered("Cash", font="Helvetica", size=8, max_width=200) == ["Cash"]


def test_long_text_wraps_within_the_printable_width():
    from reportlab.pdfbase.pdfmetrics import stringWidth

    text = "Main Bazaar, Shop #14, Near the Old Clock Tower, Lahore  0300-1234567"
    max_width = 72 * 2.834  # ~72mm in points, the receipt's usable width
    lines = _wrap_centered(text, font="Courier", size=8, max_width=max_width)
    assert len(lines) > 1  # this string is long enough that it must wrap
    for line in lines:
        assert stringWidth(line, "Courier", 8) <= max_width
    # no words were dropped or reordered
    assert " ".join(lines).split() == text.split()


def test_a_long_shop_contact_does_not_run_off_the_receipt(sale):
    settings_service.set(
        "shop.contact",
        "Main Bazaar, Shop #14, Near the Old Clock Tower, Lahore  0300-1234567",
    )
    db.session.commit()
    pdf = render_pdf(build_receipt(sale))
    assert pdf.startswith(b"%PDF-")  # renders without error either way


# --- issue_receipt: the printer decision -------------------------

def test_no_printer_configured_falls_back_to_pdf(sale):
    # default: receipt.printer.kind is unset -> 'none'
    outcome = receipts.issue_receipt(sale)
    assert outcome.printed is False
    assert outcome.medium == "pdf"


def test_an_unreachable_network_printer_falls_back_to_pdf(sale):
    settings_service.set("receipt.printer.kind", "network")
    settings_service.set("receipt.printer.host", "203.0.113.9")  # TEST-NET-3, unroutable
    settings_service.set("receipt.printer.timeout_seconds", "1")
    db.session.commit()
    outcome = receipts.issue_receipt(sale)
    assert outcome.printed is False and outcome.medium == "pdf"


def test_a_working_printer_prints(sale, tmp_path):
    dev = tmp_path / "lp0"
    settings_service.set("receipt.printer.kind", "file")
    settings_service.set("receipt.printer.device_file", str(dev))
    db.session.commit()

    outcome = receipts.issue_receipt(sale)
    assert outcome.printed is True and outcome.medium == "thermal"
    assert sale.invoice_number.encode() in dev.read_bytes()


@pytest.mark.parametrize(
    "settings",
    [
        {"receipt.printer.kind": "network"},  # no host
        {"receipt.printer.kind": "file"},  # no device_file
        {"receipt.printer.kind": "serial"},  # no serial_device
        {"receipt.printer.kind": "usb"},  # no vendor/product
        {"receipt.printer.kind": "telepathy"},  # unknown
    ],
)
def test_a_misconfigured_printer_is_unavailable_not_a_crash(app, settings):
    for k, v in settings.items():
        settings_service.set(k, v)
    db.session.commit()
    with pytest.raises(printer.PrinterUnavailable):
        printer.send(b"anything")


def test_issue_receipt_never_raises(sale, monkeypatch):
    def boom(_):
        raise RuntimeError("render blew up")

    monkeypatch.setattr(receipts, "render_escpos", boom)
    outcome = receipts.issue_receipt(sale)  # must not raise
    assert outcome.printed is False and outcome.medium == "pdf"


# --- through the till route -------------------------------------

def test_checkout_completes_and_offers_a_pdf_when_no_printer(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=10_000,
                             reason="in", user_id=seeded["admin"].id)
    login("T1", CASHIER_PASSWORD)
    client.post("/till/add", data={"product_id": p.id}, follow_redirects=True)
    resp = client.post(
        "/till/checkout",
        data={"payment_method": "cash", "amount_tendered": "500"},
        follow_redirects=True,
    )
    assert b"Sale complete" in resp.data
    assert b"Printer unavailable" in resp.data

    from sukoon.models import Sale

    sale_id = db.session.query(Sale).one().id
    pdf = client.get(f"/till/receipt/{sale_id}.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF-")


def test_reprint_route_reports_the_outcome(client, seeded, login):
    seed_invoice_counter()
    p = inv.create_product(name="Soap", sell_price_paisa=15_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=10_000,
                             reason="in", user_id=seeded["admin"].id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=15_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id, now=JAN,
    )
    login("T1", CASHIER_PASSWORD)
    resp = client.post(f"/till/receipt/{sale.id}/reprint", follow_redirects=True)
    assert b"Printer unavailable" in resp.data
