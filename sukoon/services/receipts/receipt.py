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
from sukoon.models import Sale, User
from sukoon.services import settings_service

_WIDTH_CHARS = 42  # a common 80 mm / Font A column count
_SHOP_NAME_DEFAULT = "Al-Rehman General Store"


@dataclass
class ReceiptLine:
    name: str
    quantity_text: str
    line_total_paisa: int


@dataclass
class ReceiptData:
    invoice_number: str
    when: datetime
    cashier_name: str
    lines: list[ReceiptLine]
    subtotal_paisa: int
    total_paisa: int
    payment_method: str
    shop_name: str = _SHOP_NAME_DEFAULT
    shop_contact: str | None = None
    amount_tendered_paisa: int | None = None
    change_paisa: int | None = None
    customer_name: str | None = None
    terminal_label: str | None = None  # ADR-0023; None on sales rung before it existed
    footer: str = "Thank you. Come again."


def _rupees(paisa: int | None) -> str:
    return "-" if paisa is None else f"Rs {paisa // 100:,}"


def _qty_text(quantity_milli: int) -> str:
    whole = quantity_milli / 1000
    return f"{int(whole)}" if quantity_milli % 1000 == 0 else f"{whole:g}"


def build_receipt(sale: Sale) -> ReceiptData:
    cashier = db.session.get(User, sale.user_id)
    customer = None
    if sale.customer_id is not None:
        from sukoon.models import Customer

        c = db.session.get(Customer, sale.customer_id)
        customer = c.name if c else None
    return ReceiptData(
        invoice_number=sale.invoice_number,
        when=sale.created_at,
        cashier_name=cashier.name if cashier else "—",
        lines=[
            ReceiptLine(
                name=item.product_name_snapshot,
                quantity_text=_qty_text(item.quantity_milli),
                line_total_paisa=item.line_total_paisa,
            )
            for item in sale.items
        ],
        subtotal_paisa=sale.subtotal_paisa,
        total_paisa=sale.total_paisa,
        payment_method=sale.payment_method,
        shop_name=settings_service.get("shop.name", _SHOP_NAME_DEFAULT),
        shop_contact=settings_service.get("shop.contact"),
        amount_tendered_paisa=sale.amount_tendered_paisa,
        change_paisa=sale.change_paisa,
        terminal_label=sale.terminal_label,
        customer_name=customer,
    )


# --- plain-text body, shared by both renderers --------------------------


def _row(left: str, right: str, width: int = _WIDTH_CHARS) -> str:
    room = width - len(right)
    return f"{left[:room].ljust(room)}{right}"


def receipt_body(data: ReceiptData) -> list[str]:
    """Everything below the shop-name header, as aligned text lines. Both
    renderers lay this out identically — that is what makes the printed and the
    PDF receipt say exactly the same thing. The header (shop name, contact) is
    drawn by each renderer in its own emphasis."""
    rule = "-" * _WIDTH_CHARS
    out: list[str] = [
        _row("Invoice", data.invoice_number),
        _row("Date", data.when.strftime("%Y-%m-%d %H:%M")),
        _row("Cashier", data.cashier_name),
    ]
    if data.terminal_label:
        out.append(_row("Till", data.terminal_label))
    if data.customer_name:
        out.append(_row("Customer", data.customer_name))
    out.append(rule)
    for line in data.lines:
        out.append(line.name[:_WIDTH_CHARS])
        out.append(_row(f"  {line.quantity_text}", _rupees(line.line_total_paisa)))
    out += [
        rule,
        _row("Subtotal", _rupees(data.subtotal_paisa)),
        _row("TOTAL", _rupees(data.total_paisa)),
        _row("Paid by", data.payment_method.title()),
    ]
    if data.payment_method == "cash" and data.amount_tendered_paisa is not None:
        out.append(_row("Cash", _rupees(data.amount_tendered_paisa)))
        out.append(_row("Change", _rupees(data.change_paisa)))
    out += ["", data.footer]
    return out


# --- ESC/POS ---------------------------------------------------------


def render_escpos(data: ReceiptData) -> bytes:
    """ESC/POS command bytes for a thermal printer. Built with a Dummy device so
    this stays pure — the bytes are the same ones a real printer would receive."""
    d = Dummy()
    d.set(align="center", bold=True, double_height=True)
    d.text(data.shop_name + "\n")
    d.set(align="center", bold=False, double_height=False)
    if data.shop_contact:
        d.text(data.shop_contact + "\n")
    d.text("\n")
    d.set(align="left")
    for row in receipt_body(data):
        d.text(row + "\n")
    d.text("\n\n")
    d.cut()
    return d.output


# --- PDF fallback (80 mm roll) -------------------------------------


def _wrap_centered(text: str, *, font: str, size: int, max_width: float) -> list[str]:
    """Greedy word-wrap so a long shop name/contact never runs off an 80 mm
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
    line_h = 12
    width = 80 * mm
    printable = width - 8 * mm
    logo_size = 7 * mm

    contact_lines = (
        _wrap_centered(data.shop_contact, font="Courier", size=8, max_width=printable)
        if data.shop_contact
        else []
    )
    footer_lines = (
        _wrap_centered(
            f"Questions about this bill? {data.shop_contact}",
            font="Helvetica", size=7, max_width=printable,
        )
        if data.shop_contact
        else []
    )

    height = (
        16 * mm + logo_size  # top margin + logomark
        + line_h  # shop name
        + line_h * len(contact_lines)
        + 4 + line_h * len(body)  # the shared body
        + line_h * len(footer_lines)
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
    c.drawCentredString(width / 2, y, data.shop_name)
    y -= line_h + 2
    c.setFont("Courier", 8)
    for line in contact_lines:
        c.drawCentredString(width / 2, y, line)
        y -= line_h
    y -= 4

    for row in body:
        c.drawString(4 * mm, y, row)
        y -= line_h

    if footer_lines:
        y -= 2
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0x86 / 255, 0x86 / 255, 0x8B / 255)
        for line in footer_lines:
            c.drawCentredString(width / 2, y, line)
            y -= line_h

    c.showPage()
    c.save()
    return buf.getvalue()
