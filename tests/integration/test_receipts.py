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
    WIDTH_KEY,
    _wrap_centered,
    build_receipt,
    receipt_body,
    render_escpos,
    render_pdf,
    render_test_escpos,
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
    assert data.shop_name == "Al-Rehman General Store"
    assert [line.name for line in data.lines] == ["Milk 1L", "Rice loose"]
    assert data.total_paisa == sale.total_paisa
    assert data.change_paisa == 100_000 - sale.total_paisa


def test_the_shop_name_address_and_phone_come_from_settings(sale):
    from sukoon.services import shop_profile

    shop_profile.save(name="Nizami Store", address="Main Bazaar, Johar Town, Lahore",
                      phone="0300 1234567")
    db.session.commit()
    data = build_receipt(sale)
    assert (data.shop_name, data.shop_address, data.shop_phone) == (
        "Nizami Store", "Main Bazaar, Johar Town, Lahore", "0300 1234567")
    tail = receipt_body(data)[-4:]
    assert [line.strip() for line in tail] == [
        "Thank you for shopping with us!", "NIZAMI STORE", "Main Bazaar, Johar Town, Lahore",
        "Ph: 0300 1234567"]


def test_the_old_contact_setting_is_read_as_the_address(sale):
    settings_service.set("shop.contact", "Gulberg, Lahore")
    db.session.commit()
    assert build_receipt(sale).shop_address == "Gulberg, Lahore"


def test_no_cashier_and_no_till_on_the_receipt(cashier):
    """The client's request, 2026-10-29 (ADR-0046 §3)."""
    milk = inv.create_product(name="Milk 1L", sell_price_paisa=28_000)
    inv.apply_stock_movement(product=milk, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=cashier.id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=milk, quantity_milli=1_000, unit_price_paisa=28_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=cashier.id, now=JAN, terminal_label="Till 2",
    )
    body = " ".join(receipt_body(build_receipt(sale)))
    raw = render_escpos(build_receipt(sale))
    assert "Till" not in body and b"Till 2" not in raw
    assert "Sana" not in body and "Cashier" not in body and b"Sana" not in raw


def test_the_receipt_prints_the_shops_time_not_utc(sale):
    # ADR-0024: a sale rung at 14:30 UTC is 19:30 in Pakistan. (`now=` on
    # record_sale only drives the invoice year; created_at is pinned here.)
    sale.created_at = JAN
    body = " ".join(receipt_body(build_receipt(sale)))
    assert "Date: 05-Jan-2026" in body and "07:30 PM" in body and "02:30" not in body
    assert b"07:30 PM" in render_escpos(build_receipt(sale))


def test_the_shop_timezone_setting_is_honoured(sale):
    sale.created_at = JAN
    settings_service.set("shop.timezone", "UTC")
    db.session.commit()
    assert "02:30 PM" in " ".join(receipt_body(build_receipt(sale)))


@pytest.mark.parametrize("when, day, time", [
    (datetime(2026, 10, 28, 0, 5), "28-Oct-2026", "12:05 AM"),
    (datetime(2026, 10, 28, 12, 0), "28-Oct-2026", "12:00 PM"),
    (datetime(2026, 1, 5, 9, 7), "05-Jan-2026", "09:07 AM"),
    (datetime(2026, 12, 31, 23, 59), "31-Dec-2026", "11:59 PM"),
])
def test_the_date_reads_like_the_big_stores(when, day, time):
    from sukoon.services.receipts.receipt import compute_receipt_date

    assert compute_receipt_date(when) == (day, time)


def test_items_print_as_a_table_in_capitals(sale):
    body = receipt_body(build_receipt(sale))
    head = next(r for r in body if r.startswith("ITEM"))
    assert head.split() == ["ITEM", "QTY", "RATE", "AMOUNT"] and len(head) == 48
    milk = next(r for r in body if r.startswith("MILK 1L"))
    assert milk.split() == ["MILK", "1L", "2", "280.00", "560.00"] and len(milk) == 48
    assert any(r.startswith("RICE LOOSE") for r in body)
    assert "Milk 1L" not in " ".join(body)


def test_a_long_item_name_gets_its_own_line_above_its_figures(cashier):
    seed_invoice_counter()
    p = inv.create_product(name="Pedia Sure Abbot Strawberry 400g", sell_price_paisa=155_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=5_000,
                             reason="in", user_id=cashier.id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=1_000, unit_price_paisa=155_000,
                        quantity_source="stepper")],
        payment_method="card", user_id=cashier.id, now=JAN)
    body = receipt_body(build_receipt(sale))
    i = body.index("PEDIA SURE ABBOT STRAWBERRY 400G")
    assert body[i + 1].split() == ["1", "1550.00", "1,550.00"]
    assert "Paid by" in body[body.index(next(r for r in body if r.startswith("NET AMOUNT"))) + 1]


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


def test_a_long_shop_address_wraps_instead_of_running_off(sale):
    settings_service.set(
        "shop.address",
        "Main Bazaar, Shop #14, Near the Old Clock Tower, Opposite Jamia Masjid, Lahore",
    )
    db.session.commit()
    data = build_receipt(sale)
    body = receipt_body(data)
    assert all(len(row) <= data.width for row in body)
    assert "Opposite Jamia Masjid, Lahore" in " ".join(body)
    assert render_pdf(data).startswith(b"%PDF-")


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


# --- paisa and the bill's rounding (ADR-0045) ------------------------------------------------

def test_a_paisa_bill_is_exact_to_the_last_line(app, cashier):
    """ADR-0046: no rounding — Rs 561.50 is the total, and the change from Rs 600 is Rs 38.50."""
    seed_invoice_counter()
    biscuits = inv.create_product(name="Biscuits", sell_price_paisa=15_050)
    soap = inv.create_product(name="Soap", sell_price_paisa=11_000)
    for p in (biscuits, soap):
        inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=10_000,
                                 reason="in", user_id=cashier.id)
    sale = sales_service.record_sale(
        lines=[CartLine(product=biscuits, quantity_milli=3_000, unit_price_paisa=15_050,
                        quantity_source="stepper"),
               CartLine(product=soap, quantity_milli=1_000, unit_price_paisa=11_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=cashier.id, amount_tendered_paisa=60_000, now=JAN)
    body = receipt_body(build_receipt(sale))
    rows = {r.split()[0]: r for r in body if r.strip()}
    assert rows["BISCUITS"].split() == ["BISCUITS", "3", "150.50", "451.50"]
    assert rows["SOAP"].split() == ["SOAP", "1", "110.00", "110.00"]
    assert rows["NET"].split() == ["NET", "AMOUNT", "Rs", "561.50"]
    assert rows["Cash"].split() == ["Cash", "600.00"]
    assert rows["Change"].split() == ["Change", "38.50"]
    assert rows["Items:"].split() == ["Items:", "2", "Qty:", "4"]
    assert "Rounding" not in " ".join(body) and "Subtotal" not in " ".join(body)
    assert all(len(row) <= 48 for row in body)  # 80 mm default
    assert render_pdf(build_receipt(sale)).startswith(b"%PDF")


def test_net_amount_prints_bold_and_tall(sale):
    out = render_escpos(build_receipt(sale))
    net = out.index(b"NET AMOUNT")
    assert b"\x1bE\x01\x1bG\x01\x1d!\x01" in out[net - 12:net]  # bold + double height, just before
    assert out.index(b"\x1d!\x00", net) < out.index(b"Paid by")  # and back to normal after


def test_there_is_never_a_rounding_line(sale):
    assert "Rounding" not in "\n".join(receipt_body(build_receipt(sale)))


# --- receipt width for 80 mm paper (2026-10-28) ---------------------------------------------

def test_an_80mm_receipt_uses_48_characters_by_default(sale):
    data = build_receipt(sale)
    body = receipt_body(data)
    assert data.width == 48
    assert "-" * 48 in body and all(len(row) <= 48 for row in body)
    assert any(len(row) == 48 for row in body if row.startswith("NET AMOUNT"))  # right-aligned


@pytest.mark.parametrize("chars", [42, 32])
def test_the_chosen_width_lays_out_every_line(sale, chars):
    settings_service.set(WIDTH_KEY, chars)
    db.session.commit()
    body = receipt_body(build_receipt(sale))
    assert "-" * chars in body and all(len(row) <= chars for row in body)


def test_an_unknown_width_falls_back_to_80mm(sale):
    settings_service.set(WIDTH_KEY, 77)
    db.session.commit()
    assert build_receipt(sale).width == 48


def test_the_shop_name_prints_large_when_it_fits_and_returns_to_normal(sale):
    out = render_escpos(build_receipt(sale))
    # GS ! n — the size command the shop's printer honours (it ignored ESC !, 2026-10-28):
    # 0x11 = double width + double height, 0x00 = normal
    big, normal = b"\x1d!\x11", b"\x1d!\x00"
    name = out.index(b"Al-Rehman General Store")
    assert out.rindex(big, 0, name) < name < out.index(normal, name)
    assert b"\x1bE\x01" in out[:name] and b"\x1bG\x01" in out[:name]  # bold, both ways
    assert b"\x1bE\x00" in out[name:] and b"\x1bG\x00" in out[name:]  # and off again
    assert out.index(b"Invoice") > out.index(normal, name)  # the body prints normal size


def test_a_long_shop_name_is_double_height_only_and_wrapped(sale):
    settings_service.set("shop.name", "Al-Rehman General Store and Super Mart Johar Town")
    db.session.commit()
    out = render_escpos(build_receipt(sale))
    assert b"\x1d!\x11" not in out and b"\x1d!\x01" in out  # double height only
    assert b"Johar\nTown" in out  # wrapped to the 48-character line, not cut off


def test_the_test_print_shows_a_ruler_for_every_width():
    raw = render_test_escpos("Nizami Store", "28 Oct 2026", 48)
    assert raw.index(b"\x1d!\x11") < raw.index(b"Nizami Store")  # the large name, GS !
    out = raw.decode("latin-1")
    for chars in (48, 42, 32):
        assert f"{chars} characters:" in out
        assert "\n" + ("1234567890" * 5)[:chars] + "\n" in out
    assert "Set now: 48 characters." in out


def test_the_pdf_fits_any_width(sale):
    for chars in (48, 42, 32):
        settings_service.set(WIDTH_KEY, chars)
        db.session.commit()
        assert render_pdf(build_receipt(sale)).startswith(b"%PDF")
