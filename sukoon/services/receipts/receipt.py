"""Sale receipt — content model, ESC/POS rendering, and an 80 mm PDF fallback
(Development Specification Phase 3 step 5; Design System Figure 9).

No Flask import (ADR-0003 §1). ``build_receipt`` reads a ``Sale``; ``render_escpos``
and ``render_pdf`` are pure over the resulting ``ReceiptData``. Sending bytes to a
real printer, and the "printer offline -> PDF" decision, live in
``receipts.printer`` and ``receipts.issue_receipt``.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from escpos.printer import Dummy
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from sukoon.extensions import db
from sukoon.models import Sale
from sukoon.services import clock, settings_service, shop_profile

# Characters per line in the printer's normal font (Font A). 80 mm printers are usually 48;
# some are 42. A setting, not a constant, because only the printer's own self-test page can say,
# and the Settings test print shows a ruler for each so the shop can pick (2026-10-28).
WIDTH_KEY = "receipt.chars_per_line"
RECEIPT_WIDTHS: tuple[tuple[int, str], ...] = (
    (48, "80 mm paper — 48 characters a line (most 80 mm printers)"),
    (42, "80 mm paper — 42 characters a line"),
    (32, "58 mm paper — 32 characters a line"),
)
DEFAULT_WIDTH = 48
_WIDTH_CHARS = 42  # the narrowest 80 mm width: what a ReceiptData built by hand defaults to


def receipt_width() -> int:
    """The shop's chosen characters per line; the 80 mm default if unset or unrecognised."""
    value = settings_service.get_int(WIDTH_KEY, DEFAULT_WIDTH)
    return value if value in {w for w, _ in RECEIPT_WIDTHS} else DEFAULT_WIDTH


_THANKS = "Thank you for shopping with us!"
_NET_LABEL = "NET AMOUNT"  # the one body row both renderers print in bold
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_PAID_BY = {"cash": "Cash", "card": "Card", "credit": "Khata"}


@dataclass
class ReceiptLine:
    name: str
    quantity_milli: int
    unit_price_paisa: int
    line_total_paisa: int


@dataclass
class ReceiptData:
    """What a receipt says. Laid out like the big stores' (Imtiaz, Al-Fatah — the client's request,
    2026-10-29): an item table in capitals, the date as 28-Oct-2026, no cashier or till name, the
    exact total, and the shop's name, address and phone at the bottom."""

    invoice_number: str
    when: datetime
    lines: list[ReceiptLine]
    total_paisa: int
    payment_method: str
    shop_name: str = shop_profile.DEFAULT_NAME
    shop_address: str | None = None
    shop_phone: str | None = None
    amount_tendered_paisa: int | None = None
    change_paisa: int | None = None
    customer_name: str | None = None
    width: int = _WIDTH_CHARS  # characters per line (receipt_width())


def compute_receipt_date(when: datetime) -> tuple[str, str]:
    """``("28-Oct-2026", "07:30 PM")``; month names in English whatever the PC's language."""
    return (f"{when.day:02d}-{_MONTHS[when.month - 1]}-{when.year}",
            f"{when.hour % 12 or 12:02d}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}")


def _amount(paisa: int) -> str:
    """``1,234.50`` — always two decimals, the way a till roll prints money."""
    sign = "-" if paisa < 0 else ""
    whole, part = divmod(abs(paisa), 100)
    return f"{sign}{whole:,}.{part:02d}"


def _qty(quantity_milli: int) -> str:
    whole = quantity_milli / 1000
    return f"{int(whole)}" if quantity_milli % 1000 == 0 else f"{whole:g}"


def build_receipt(sale: Sale) -> ReceiptData:
    customer = None
    if sale.customer_id is not None:
        from sukoon.models import Customer

        c = db.session.get(Customer, sale.customer_id)
        customer = c.display_name if c else None
    shop = shop_profile.get()
    return ReceiptData(
        invoice_number=sale.invoice_number,
        when=clock.to_shop_time(sale.created_at),  # ADR-0024: the shop's clock
        lines=[
            ReceiptLine(
                name=item.product_name_snapshot,
                quantity_milli=item.quantity_milli,
                unit_price_paisa=item.unit_price_paisa_snapshot,
                line_total_paisa=item.line_total_paisa,
            )
            for item in sale.items
        ],
        total_paisa=sale.total_paisa,
        payment_method=sale.payment_method,
        shop_name=shop.name,
        shop_address=shop.address,
        shop_phone=shop.phone,
        amount_tendered_paisa=sale.amount_tendered_paisa,
        change_paisa=sale.change_paisa,
        customer_name=customer,
        width=receipt_width(),
    )


# --- plain-text body, shared by both renderers --------------------------


def _row(left: str, right: str, width: int = _WIDTH_CHARS) -> str:
    room = max(width - len(right) - 1, 0) if left and right else width - len(right)
    return f"{left[:room].ljust(room)}{' ' if left and right else ''}{right}"


def _item_rows(line: ReceiptLine, w: int) -> list[str]:
    """One table row: ITEM QTY RATE AMOUNT. A name too long for its column gets a line of its own
    above the figures. Below 40 characters (58 mm paper) there is no room for columns, so the
    figures go on a second line as ``qty x rate``."""
    name = line.name.upper()
    # the rate without thousands commas, as till rolls print it: 10550.00 still fits its column
    qty, rate = _qty(line.quantity_milli), _amount(line.unit_price_paisa).replace(",", "")
    amount = _amount(line.line_total_paisa)
    if w < 40:
        return _wrap_chars(name, w) + [_row(f"  {qty} x {rate}", amount, w)]
    item_w = w - 26  # QTY 6 + RATE 9 + AMOUNT 11
    figures = f"{qty:>6}{rate:>9}{amount:>11}"
    if len(name) < item_w:  # strictly less: at least one space before the quantity
        return [f"{name:<{item_w}}{figures}"]
    return _wrap_chars(name, w) + [f"{'':<{item_w}}{figures}"]


def _centre(text: str, w: int) -> list[str]:
    return [line.center(w).rstrip() for line in _wrap_chars(text, w)]


def receipt_body(data: ReceiptData) -> list[str]:
    """Everything below the shop-name header, as aligned text lines. Both renderers lay this out
    identically — that is what makes the printed and the PDF receipt say exactly the same thing.
    The large shop name at the top is drawn by each renderer in its own emphasis."""
    w = data.width
    rule = "-" * w
    day, time = compute_receipt_date(data.when)
    out: list[str] = [
        _row(f"Invoice: {data.invoice_number}", "", w),
        _row(f"Date: {day}", time, w),
    ]
    if data.customer_name:
        out.append(f"Khata: {data.customer_name}"[:w])
    out.append(rule)
    if w >= 40:
        out.append(f"{'ITEM':<{w - 26}}{'QTY':>6}{'RATE':>9}{'AMOUNT':>11}")
        out.append(rule)
    for line in data.lines:
        out += _item_rows(line, w)
    out.append(rule)
    out.append(_row(f"Items: {len(data.lines)}",
                    f"Qty: {_qty(sum(x.quantity_milli for x in data.lines))}", w))
    out.append(_row(_NET_LABEL, f"Rs {_amount(data.total_paisa)}", w))
    out.append(_row("Paid by", _PAID_BY.get(data.payment_method, data.payment_method.title()), w))
    if data.payment_method == "cash" and data.amount_tendered_paisa is not None:
        out.append(_row("Cash", _amount(data.amount_tendered_paisa), w))
        out.append(_row("Change", _amount(data.change_paisa or 0), w))
    out.append(rule)
    out += _centre(_THANKS, w)
    out += _centre(data.shop_name.upper(), w)
    if data.shop_address:
        out += _centre(data.shop_address, w)
    if data.shop_phone:
        out += _centre(f"Ph: {data.shop_phone}", w)
    return out


# --- ESC/POS ---------------------------------------------------------


def render_escpos(data: ReceiptData) -> bytes:
    """ESC/POS command bytes for a thermal printer. Built with a Dummy device so
    this stays pure — the bytes are the same ones a real printer would receive."""
    d = Dummy()
    _shop_name_escpos(d, data.shop_name, data.width)
    d.text("\n")
    d.set(align="left")
    for row in receipt_body(data):
        if row.startswith(_NET_LABEL):
            d._raw(_BOLD_ON + _SIZE_TALL)  # double height keeps the line's width
            d.text(row + "\n")
            d._raw(_SIZE_NORMAL + _BOLD_OFF)
        else:
            d.text(row + "\n")
    d.text("\n\n")
    d.cut()
    return d.output


def _wrap_chars(text: str, width: int) -> list[str]:
    """Word-wrap to a character width; a word longer than the line is cut, not lost."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word[:width]
    if current:
        lines.append(current)
    return lines


# The shop's printer (Black Copper BC-85ACG1, test prints of 2026-10-28) honoured ESC a (centring)
# but ignored ESC ! (print mode): the shop name came out the same size as everything else. So size
# is set with GS ! — the character-size command nearly every ESC/POS printer supports — and bold is
# sent both ways, ESC E (emphasis) and ESC G (double-strike), so whichever the printer knows works.
_SIZE_2X2 = b"\x1d!\x11"  # GS ! : double width and double height
_SIZE_TALL = b"\x1d!\x01"  # GS ! : double height only
_SIZE_NORMAL = b"\x1d!\x00"
_BOLD_ON = b"\x1bE\x01\x1bG\x01"
_BOLD_OFF = b"\x1bE\x00\x1bG\x00"


def _shop_name_escpos(d: Dummy, name: str, width: int) -> None:
    """The shop name centred and bold, at double width and height when it fits on a line at
    that size, else double height only; then everything back to normal. Double width halves
    the characters a line holds, so "Al-Rehman General Store" (23) fits 48 and 42."""
    big = len(name) * 2 <= width
    d.set(align="center")
    d._raw(_BOLD_ON + (_SIZE_2X2 if big else _SIZE_TALL))
    for line in _wrap_chars(name, width // 2 if big else width):
        d.text(line + "\n")
    d._raw(_SIZE_NORMAL + _BOLD_OFF)


# --- PDF fallback (80 mm roll) -------------------------------------


def _wrap_centered(text: str, *, font: str, size: int, max_width: float) -> list[str]:
    """Greedy word-wrap so a long shop name never runs off an 80 mm
    receipt — printers don't clip gracefully, they just cut the line off."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font, size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_pdf(data: ReceiptData) -> bytes:
    body = receipt_body(data)
    width = 80 * mm
    printable = width - 8 * mm
    # Courier is 0.6 em wide: the body font is sized so a full line spans the printable width.
    body_size = min(9.0, printable / (0.6 * data.width))
    line_h = max(10.0, body_size * 1.45)
    logo_size = 7 * mm
    name_lines = _wrap_centered(data.shop_name, font="Helvetica-Bold", size=12,
                                max_width=printable)

    height = (
        16 * mm + logo_size  # top margin + logomark
        + line_h * len(name_lines)  # shop name
        + 4 + line_h * len(body)  # the shared body
        + 10 * mm  # bottom margin
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    y = height - 8 * mm

    # A small drawn logomark — no image asset needed, just brand-teal shapes
    # (Design System Figure 9: "the logomark appears even on the printed
    # receipt — brand consistency extends past the screen").
    logo_x = width / 2 - logo_size / 2
    logo_y = y - logo_size
    c.setFillColorRGB(0x0E / 255, 0x6B / 255, 0x57 / 255)
    c.roundRect(logo_x, logo_y, logo_size, logo_size, 2 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0xF4 / 255, 0xC5 / 255, 0x67 / 255)
    c.circle(width / 2, logo_y + logo_size * 0.6, logo_size * 0.16, fill=1, stroke=0)
    y = logo_y - line_h

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    for line in name_lines:
        c.drawCentredString(width / 2, y, line)
        y -= line_h
    y -= 6

    for row in body:
        c.setFont("Courier-Bold" if row.startswith(_NET_LABEL) else "Courier", body_size)
        c.drawString(4 * mm, y, row)
        y -= line_h

    c.showPage()
    c.save()
    return buf.getvalue()


def render_test_escpos(shop_name: str, when: str, width: int = DEFAULT_WIDTH) -> bytes:
    """A short slip for the Settings screen's "Print a test receipt". It exists so the printer can
    be proved at installation without ringing up a real sale (ADR-0039 §3), and it shows a ruler
    for every receipt width so the shop can see which one fits its printer."""
    d = Dummy()
    _shop_name_escpos(d, shop_name, width)
    d.text("Test receipt\n")
    d.text(when + "\n\n")
    d.set(align="left")
    d.text("If you can read this, Sukoon can print.\n\n")
    d.text("Which ruler fits on ONE line?\n")
    for chars, _label in RECEIPT_WIDTHS:
        d.text(f"{chars} characters:\n")
        d.text(("1234567890" * 5)[:chars] + "\n")
    d.text(f"\nSet now: {width} characters.\n")
    d.text("Pick the longest ruler that\n")
    d.text("stayed on one line, in Settings.\n")
    d.text("\n\n")
    d.cut()
    return d.output
