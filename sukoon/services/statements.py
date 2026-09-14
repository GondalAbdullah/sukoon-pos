"""Per-customer Khata statement: assembled rows and an A4 PDF (Development Spec
Phase 4 step 4; ADR-0026 §4). No Flask.

``build_statement`` turns ledger rows into ``StatementDoc`` — every line already
worded the way a customer reads it. ``statement_text`` and ``render_pdf`` both lay
out that one document, so the fixture-tested text and the printed page can't say
different things (the same pattern as receipts).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from sukoon.extensions import db
from sukoon.models import Customer, Sale, User
from sukoon.services import clock, khata_service, ledger, settings_service

_TYPE_LABEL = {"credit_sale": "Purchase", "payment": "Payment", "refund": "Refund",
               "adjustment": "Adjustment"}


def rs(paisa: int) -> str:
    return f"Rs {abs(paisa) // 100:,}"


def balance_words(paisa: int) -> str:
    state = ledger.describe_balance(paisa)
    return {"owes": f"{rs(state.amount_paisa)} owed", "settled": "Settled",
            "in_credit": f"{rs(state.amount_paisa)} in credit"}[state.kind]


def signed(paisa: int) -> str:
    return f"+ {rs(paisa)}" if paisa > 0 else f"- {rs(paisa)}"


@dataclass(frozen=True)
class Line:
    when: str
    kind: str
    details: str
    amount: str
    balance: str
    amount_paisa: int


@dataclass(frozen=True)
class StatementDoc:
    shop_name: str
    shop_contact: str | None
    customer_name: str
    customer_phone: str | None
    period_label: str
    generated: str
    opening: str
    purchased: str
    paid: str
    refunded: str | None
    adjusted: str | None
    closing: str
    lines: list[Line]
    closing_paisa: int
    reconciles: bool


@dataclass(frozen=True)
class Period:
    key: str          # "2026-09" or "all"
    label: str        # "September 2026" or "All time"
    start: datetime | None
    end: datetime | None


def period_for(key: str | None, now: datetime | None = None) -> Period:
    now_local = clock.to_shop_time(now or datetime.now(UTC))
    if key == "all":
        return Period("all", "All time", None, None)
    try:
        year, month = (int(p) for p in (key or "").split("-"))
        datetime(year, month, 1)
    except (TypeError, ValueError):
        year, month = now_local.year, now_local.month
    start, end = clock.shop_month_bounds(year, month)
    return Period(f"{year:04d}-{month:02d}", datetime(year, month, 1).strftime("%B %Y"),
                  start, end)


def recent_periods(now: datetime | None = None, count: int = 6) -> list[Period]:
    local = clock.to_shop_time(now or datetime.now(UTC))
    out, y, m = [], local.year, local.month
    for _ in range(count):
        out.append(period_for(f"{y:04d}-{m:02d}", now))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out + [period_for("all")]


def _details(entry, sales: dict[int, Sale], users: dict[int, User]) -> str:
    parts = []
    if entry.sale_id and entry.sale_id in sales:
        parts.append(sales[entry.sale_id].invoice_number)
    is_override = entry.entry_type == "credit_sale" and entry.override_authorised_by_user_id
    if entry.note and not is_override:
        parts.append(entry.note)
    if entry.override_authorised_by_user_id:
        admin = users.get(entry.override_authorised_by_user_id)
        parts.append(f"over limit, approved by {admin.name if admin else 'an Admin'}")
    return " · ".join(parts)


def build_statement(
    customer: Customer, period: Period, *, now: datetime | None = None
) -> StatementDoc:
    entries = khata_service.entries_for(customer.id)
    st = ledger.compute_statement(entries, period.start, period.end)

    sale_ids = {r.entry.sale_id for r in st.rows if r.entry.sale_id}
    sales = {s.id: s for s in db.session.scalars(db.select(Sale).where(Sale.id.in_(sale_ids)))} \
        if sale_ids else {}
    user_ids = {r.entry.override_authorised_by_user_id for r in st.rows
                if r.entry.override_authorised_by_user_id}
    users = {u.id: u for u in db.session.scalars(db.select(User).where(User.id.in_(user_ids)))} \
        if user_ids else {}

    lines = [
        Line(
            when=clock.format_shop_time(r.entry.created_at, "%d %b %Y %H:%M"),
            kind=_TYPE_LABEL.get(r.entry.entry_type, r.entry.entry_type),
            details=_details(r.entry, sales, users),
            amount=signed(r.amount_paisa),
            balance=balance_words(r.running_paisa),
            amount_paisa=r.amount_paisa,
        )
        for r in st.rows
    ]
    return StatementDoc(
        shop_name=settings_service.get("shop.name", "Al-Rehman General Store"),
        shop_contact=settings_service.get("shop.contact"),
        customer_name=customer.name,
        customer_phone=customer.phone_raw or customer.phone_normalised,
        period_label=period.label,
        generated=clock.format_shop_time(now or datetime.now(UTC), "%d %b %Y %H:%M"),
        opening=balance_words(st.opening_paisa),
        purchased=rs(st.purchased_paisa),
        paid=rs(st.paid_paisa),
        refunded=rs(st.refunded_paisa) if st.refunded_paisa else None,
        adjusted=signed(st.adjusted_paisa) if st.adjusted_paisa else None,
        closing=balance_words(st.closing_paisa),
        lines=lines,
        closing_paisa=st.closing_paisa,
        reconciles=not st.discrepancies,
    )


def statement_text(doc: StatementDoc) -> list[str]:
    """The statement as plain lines — what the fixture test compares, and exactly
    the content the PDF draws."""
    out = [
        doc.shop_name,
        "Khata statement",
        f"Customer: {doc.customer_name}"
        + (f" ({doc.customer_phone})" if doc.customer_phone else ""),
        f"Period: {doc.period_label}",
        f"Opening balance: {doc.opening}",
        f"Purchases: {doc.purchased}",
        f"Payments: {doc.paid}",
    ]
    if doc.refunded:
        out.append(f"Refunds: {doc.refunded}")
    if doc.adjusted:
        out.append(f"Adjustments: {doc.adjusted}")
    out.append(f"Closing balance: {doc.closing}")
    out.append("---")
    if not doc.lines:
        out.append("No purchases or payments in this period.")
    for ln in doc.lines:
        out.append(" | ".join(filter(None, [ln.when, ln.kind, ln.details, ln.amount, ln.balance])))
    return out


# --- PDF (A4) -------------------------------------------------------------------------

_TEAL = (0x0E / 255, 0x6B / 255, 0x57 / 255)
_CORAL = (0xC1 / 255, 0x5B / 255, 0x45 / 255)
_MUTED = (0x86 / 255, 0x86 / 255, 0x8B / 255)
_INK = (0x1C / 255, 0x1C / 255, 0x1E / 255)


def _fit(text: str, font: str, size: float, width: float) -> str:
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


def render_pdf(doc: StatementDoc) -> bytes:
    buf = io.BytesIO()
    page_w, page_h = A4
    left, right = 18 * mm, page_w - 18 * mm
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Khata statement — {doc.customer_name} — {doc.period_label}")
    cols = {"when": left, "kind": left + 36 * mm, "details": left + 58 * mm,
            "amount": right - 38 * mm, "balance": right}
    page = 1

    def header() -> float:
        y = page_h - 20 * mm
        c.setFillColorRGB(*_TEAL)
        c.roundRect(left, y - 7 * mm, 9 * mm, 9 * mm, 2.4 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0xF4 / 255, 0xC5 / 255, 0x67 / 255)
        c.circle(left + 4.5 * mm, y - 1.6 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left + 13 * mm, y - 3 * mm, doc.shop_name)
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(*_MUTED)
        if doc.shop_contact:
            contact = _fit(doc.shop_contact, "Helvetica", 8.5, 110 * mm)
            c.drawString(left + 13 * mm, y - 7.5 * mm, contact)
        c.drawRightString(right, y - 3 * mm, f"Khata statement · {doc.period_label}")
        c.drawRightString(right, y - 7.5 * mm, f"Printed {doc.generated} · page {page}")
        return y - 16 * mm

    def table_head(y: float) -> float:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColorRGB(*_MUTED)
        c.drawString(cols["when"], y, "DATE")
        c.drawString(cols["kind"], y, "TYPE")
        c.drawString(cols["details"], y, "DETAILS")
        c.drawRightString(cols["amount"], y, "AMOUNT")
        c.drawRightString(cols["balance"], y, "BALANCE")
        c.setStrokeColorRGB(0.9, 0.9, 0.88)
        c.line(left, y - 2.5 * mm, right, y - 2.5 * mm)
        return y - 8 * mm

    y = header()
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, doc.customer_name)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*_MUTED)
    if doc.customer_phone:
        c.drawString(left, y - 5.5 * mm, doc.customer_phone)
    y -= 15 * mm

    summary = [("Opening balance", doc.opening), ("Purchases", doc.purchased),
               ("Payments", doc.paid)]
    if doc.refunded:
        summary.append(("Refunds", doc.refunded))
    if doc.adjusted:
        summary.append(("Adjustments", doc.adjusted))
    box_w = (right - left - 3 * mm * len(summary)) / (len(summary) + 1)
    x = left
    for label, value in summary:
        c.setFillColorRGB(0.965, 0.96, 0.945)
        c.roundRect(x, y - 13 * mm, box_w, 15 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColorRGB(*_MUTED)
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(x + 3 * mm, y - 3 * mm, label.upper())
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(x + 3 * mm, y - 9.5 * mm, _fit(value, "Helvetica-Bold", 10.5, box_w - 6 * mm))
        x += box_w + 3 * mm
    owes = doc.closing_paisa > 0
    c.setFillColorRGB(*((0.984, 0.933, 0.918) if owes else (0.906, 0.953, 0.937)))
    c.roundRect(x, y - 13 * mm, right - x, 15 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColorRGB(*(_CORAL if owes else _TEAL))
    c.setFont("Helvetica-Bold", 6.8)
    c.drawString(x + 3 * mm, y - 3 * mm, "CLOSING BALANCE")
    c.setFont("Helvetica-Bold", 10.5)
    closing = _fit(doc.closing, "Helvetica-Bold", 10.5, right - x - 6 * mm)
    c.drawString(x + 3 * mm, y - 9.5 * mm, closing)
    y -= 24 * mm

    y = table_head(y)
    if not doc.lines:
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*_MUTED)
        c.drawString(left, y, "No purchases or payments in this period.")
    for ln in doc.lines:
        if y < 22 * mm:
            c.showPage()
            page += 1
            y = table_head(header())
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(*_INK)
        c.drawString(cols["when"], y, ln.when)
        c.drawString(cols["kind"], y, ln.kind)
        c.setFillColorRGB(*_MUTED)
        c.drawString(cols["details"], y, _fit(ln.details, "Helvetica", 8.5,
                                               cols["amount"] - 30 * mm - cols["details"]))
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColorRGB(*(_CORAL if ln.amount_paisa > 0 else _TEAL))
        c.drawRightString(cols["amount"], y, ln.amount)
        c.setFillColorRGB(*_INK)
        c.drawRightString(cols["balance"], y, ln.balance)
        c.setStrokeColorRGB(0.95, 0.95, 0.93)
        c.line(left, y - 2.8 * mm, right, y - 2.8 * mm)
        y -= 7.5 * mm

    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(*_MUTED)
    c.drawString(left, 12 * mm, "Positive amounts are purchases added to the Khata; "
                               "negative amounts are payments and refunds.")
    c.showPage()
    c.save()
    return buf.getvalue()
