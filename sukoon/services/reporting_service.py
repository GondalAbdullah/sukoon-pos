"""Reports and the Insights dashboard (Development Spec Phase 6; ADR-0034). No Flask.

Totals, categories, products and estimated profit are SQL aggregates — the per-line cost
rounding included, in integer SQL identical to ``money.line_total_for_quantity``. Time
buckets (by day, by hour) read only timestamp and amount and bucket in shop time in
Python, because SQLite has no timezone conversion (ADR-0034 §11).

Every report is built as one ``ReportDoc``; the screen, the CSV and the PDF all lay out
that same document, so their figures can't disagree (ADR-0034 §10).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sukoon.extensions import db
from sukoon.models import (
    Category,
    Customer,
    Product,
    Refund,
    RefundItem,
    Sale,
    SaleItem,
)
from sukoon.services import clock, inventory_service, khata_service, ledger, money

# half-up to whole rupees, exactly money.line_total_for_quantity, for non-negative values
_COST_SQL = "((product.cost_price_paisa * {qty} + 50000) / 100000) * 100"


# --- periods (ADR-0034 §3–4) -------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    key: str  # "today" | "week" | "month" | "custom"
    label: str
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive


def _local_midnight(d: date) -> datetime:
    """Midnight on ``d`` in the shop's zone, with that date's own offset (zoneinfo resolves
    it), so this stays right even for a shop.timezone that observes daylight saving."""
    try:
        zone = ZoneInfo(clock.shop_zone_name())
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(clock.DEFAULT_TIMEZONE)
    return datetime(d.year, d.month, d.day, tzinfo=zone)


def preset(name: str, now: datetime | None = None) -> Period:
    now = now or datetime.now(UTC)
    today = clock.to_shop_time(now).date()
    if name == "week":
        monday = today - timedelta(days=today.weekday())
        start = _local_midnight(monday)
        end = _local_midnight(monday + timedelta(days=7))
        label = (
            f"This week ({monday.day} {monday:%b} – {(monday + timedelta(days=6)).day} "
            f"{monday + timedelta(days=6):%b})"
        )
    elif name == "month":
        start = _local_midnight(today.replace(day=1))
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = _local_midnight(nxt)
        label = f"This month ({today:%B %Y})"
    else:
        name = "today"
        start = _local_midnight(today)
        end = _local_midnight(today + timedelta(days=1))
        label = f"Today ({today.day} {today:%b %Y})"
    return Period(name, label, start.astimezone(UTC), end.astimezone(UTC))


class PeriodError(ValueError):
    pass


def custom(date_from: str | None, date_to: str | None) -> Period:
    try:
        a = date.fromisoformat((date_from or "").strip())
        b = date.fromisoformat((date_to or "").strip())
    except ValueError as exc:
        raise PeriodError("Choose both dates.") from exc
    if b < a:
        raise PeriodError("The end date is before the start date.")
    label = f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}" if a != b else f"{a.day} {a:%b %Y}"
    return Period(
        "custom",
        label,
        _local_midnight(a).astimezone(UTC),
        _local_midnight(b + timedelta(days=1)).astimezone(UTC),
    )


def comparison(period: Period, now: datetime | None = None) -> Period:
    """The period this one is compared with (ADR-0034 §4): same weekday last week / the
    previous week or month, up to the same point; for custom, the same length just before."""
    now = now or datetime.now(UTC)
    cutoff = min(max(now, period.start), period.end)
    if period.key == "today":
        return Period(
            "prev",
            "same day last week",
            period.start - timedelta(days=7),
            cutoff - timedelta(days=7),
        )
    if period.key == "week":
        return Period(
            "prev", "last week", period.start - timedelta(days=7), cutoff - timedelta(days=7)
        )
    if period.key == "month":
        local_start = clock.to_shop_time(period.start).date()
        prev_first = (local_start - timedelta(days=1)).replace(day=1)
        prev_start = _local_midnight(prev_first).astimezone(UTC)
        elapsed = cutoff - period.start
        return Period("prev", "last month", prev_start, min(prev_start + elapsed, period.start))
    length = period.end - period.start
    return Period("prev", "the period before", period.start - length, period.start)


# --- sales ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SalesTotals:
    count: int
    gross_paisa: int
    refunds_paisa: int
    by_method: dict[str, int]

    @property
    def net_paisa(self) -> int:
        return self.gross_paisa - self.refunds_paisa


def _in(col, period: Period):
    return db.and_(col >= period.start.replace(tzinfo=None), col < period.end.replace(tzinfo=None))


def sales_totals(period: Period) -> SalesTotals:
    rows = db.session.execute(
        db.select(Sale.payment_method, db.func.count(Sale.id), db.func.sum(Sale.total_paisa))
        .where(_in(Sale.created_at, period))
        .group_by(Sale.payment_method)
    ).all()
    refunds = (
        db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(Refund.total_paisa), 0)).where(
                Refund.status == "approved", _in(Refund.resolved_at, period)
            )
        )
        or 0
    )
    by_method = {m: int(t or 0) for m, _c, t in rows}
    return SalesTotals(
        sum(c for _m, c, _t in rows), sum(by_method.values()), int(refunds), by_method
    )


def _shop_zone():
    """Resolve the shop's zone ONCE per report. Converting each row through
    clock.to_shop_time read the timezone setting from the database per sale — 10,000
    queries on 10,000 sales (3+ seconds), found by the Phase 6 performance test."""
    try:
        return ZoneInfo(clock.shop_zone_name())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(clock.DEFAULT_TIMEZONE)


def _local(dt: datetime, zone) -> datetime:
    return (dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt).astimezone(zone)


def _bucket(period: Period, fmt) -> dict:
    zone = _shop_zone()
    out: dict = {}
    for created, total in db.session.execute(
        db.select(Sale.created_at, Sale.total_paisa).where(_in(Sale.created_at, period))
    ):
        key = fmt(_local(created, zone))
        count, amount = out.get(key, (0, 0))
        out[key] = (count + 1, amount + total)
    return out


def sales_by_hour(period: Period) -> list[tuple[int, int, int]]:
    """(hour 0–23 shop time, sales, rupees-in-paisa) for every hour that had a sale."""
    buckets = _bucket(period, lambda t: t.hour)
    return [(h, *buckets[h]) for h in sorted(buckets)]


def sales_by_day(period: Period) -> list[tuple[date, int, int]]:
    buckets = _bucket(period, lambda t: t.date())
    zone = _shop_zone()
    refunds: dict[date, int] = {}
    for resolved, total in db.session.execute(
        db.select(Refund.resolved_at, Refund.total_paisa).where(
            Refund.status == "approved", _in(Refund.resolved_at, period)
        )
    ):
        d = _local(resolved, zone).date()
        refunds[d] = refunds.get(d, 0) + total
    days = sorted(set(buckets) | set(refunds))
    return [(d, *buckets.get(d, (0, 0)), refunds.get(d, 0)) for d in days]


def sales_by_category(period: Period) -> list[tuple[str, int]]:
    rows = db.session.execute(
        db.select(Category.name, db.func.sum(SaleItem.line_total_paisa))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(_in(Sale.created_at, period))
        .group_by(Category.name)
    ).all()
    return sorted(((name or "No category", int(t)) for name, t in rows), key=lambda r: -r[1])


def top_products(period: Period, limit: int = 10) -> list[tuple[str, int, int]]:
    """(current product name, quantity in milli-units, sales in paisa), best sellers first."""
    rows = db.session.execute(
        db.select(
            Product.name,
            db.func.sum(SaleItem.quantity_milli),
            db.func.sum(SaleItem.line_total_paisa),
        )
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(_in(Sale.created_at, period))
        .group_by(Product.id)
        .order_by(db.func.sum(SaleItem.line_total_paisa).desc())
        .limit(limit)
    ).all()
    return [(n, int(q), int(t)) for n, q, t in rows]


def recent_sales(period: Period, limit: int = 8) -> list[Sale]:
    return list(
        db.session.scalars(
            db.select(Sale)
            .where(_in(Sale.created_at, period))
            .order_by(Sale.created_at.desc(), Sale.id.desc())
            .limit(limit)
        )
    )


# --- estimated profit (ADR-0034 §2, §6) ------------------------------------------------------


@dataclass(frozen=True)
class Profit:
    net_sales_paisa: int  # every sale in the period minus approved refunds
    covered_sales_paisa: int  # the part whose products have a cost price
    estimated_cost_paisa: int
    uncovered_sales_paisa: int

    @property
    def estimated_profit_paisa(self) -> int:
        return self.covered_sales_paisa - self.estimated_cost_paisa

    @property
    def margin_percent(self) -> float | None:
        if self.covered_sales_paisa <= 0:
            return None
        return 100 * self.estimated_profit_paisa / self.covered_sales_paisa

    @property
    def coverage_percent(self) -> float | None:
        if self.net_sales_paisa <= 0:
            return None
        return 100 * self.covered_sales_paisa / self.net_sales_paisa


def _profit_parts(period: Period, *, category_id: int | None = None, by_category: bool = False):
    cost = db.literal_column(_COST_SQL.format(qty="sale_item.quantity_milli"))
    known = Product.cost_price_paisa.is_not(None)
    sale_q = (
        db.select(
            *([Product.category_id] if by_category else []),
            db.func.coalesce(db.func.sum(SaleItem.line_total_paisa), 0),
            db.func.coalesce(db.func.sum(db.case((known, SaleItem.line_total_paisa), else_=0)), 0),
            db.func.coalesce(db.func.sum(db.case((known, cost), else_=0)), 0),
        )
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(_in(Sale.created_at, period))
    )
    rcost = db.literal_column(_COST_SQL.format(qty="refund_item.quantity_milli"))
    refund_q = (
        db.select(
            *([Product.category_id] if by_category else []),
            db.func.coalesce(db.func.sum(RefundItem.line_total_paisa), 0),
            db.func.coalesce(
                db.func.sum(db.case((known, RefundItem.line_total_paisa), else_=0)), 0
            ),
            # a restocked return gives its cost back; a damaged one doesn't (§6)
            db.func.coalesce(
                db.func.sum(
                    db.case((db.and_(known, RefundItem.restock.is_(True)), rcost), else_=0)
                ),
                0,
            ),
        )
        .select_from(RefundItem)
        .join(Refund, Refund.id == RefundItem.refund_id)
        .join(SaleItem, SaleItem.id == RefundItem.sale_item_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(Refund.status == "approved", _in(Refund.resolved_at, period))
    )
    if by_category:
        sale_q = sale_q.group_by(Product.category_id)
        refund_q = refund_q.group_by(Product.category_id)
    return db.session.execute(sale_q).all(), db.session.execute(refund_q).all()


def estimated_profit(period: Period) -> Profit:
    (s,), (r,) = _profit_parts(period)
    gross, covered, cost = (int(x) for x in s)
    r_gross, r_covered, r_cost = (int(x) for x in r)
    net, cov = gross - r_gross, covered - r_covered
    return Profit(net, cov, cost - r_cost, net - cov)


def profit_by_category(period: Period) -> list[tuple[str, Profit]]:
    sales, refunds = _profit_parts(period, by_category=True)
    names = {c.id: c.name for c in db.session.scalars(db.select(Category))}
    parts: dict[int | None, list[int]] = {}
    for cat, gross, covered, cost in sales:
        parts[cat] = [int(gross), int(covered), int(cost)]
    for cat, gross, covered, cost in refunds:
        p = parts.setdefault(cat, [0, 0, 0])
        p[0] -= int(gross)
        p[1] -= int(covered)
        p[2] -= int(cost)
    out = [
        (names.get(cat, "No category") if cat else "No category", Profit(g, c, k, g - c))
        for cat, (g, c, k) in parts.items()
    ]
    return sorted(out, key=lambda r: -r[1].net_sales_paisa)


# --- point-in-time: stock and credit (ADR-0034 §7–8) ----------------------------------------


@dataclass(frozen=True)
class StockRow:
    product: Product
    category: str
    value_paisa: int | None  # None = cost unknown, never zero
    status: str  # "healthy" | "low" | "out" | "never_counted"


def stock_rows() -> list[StockRow]:
    products = list(
        db.session.scalars(
            db.select(Product).where(Product.is_active.is_(True)).order_by(Product.name)
        )
    )
    names = {c.id: c.name for c in db.session.scalars(db.select(Category))}
    counted = inventory_service.counted_product_ids(p.id for p in products)
    out = []
    for p in products:
        status = inventory_service.compute_stock_status(p)
        if p.id not in counted and p.stock_quantity_milli <= 0:
            status = "never_counted"
        value = (
            None
            if p.cost_price_paisa is None
            else money.line_total_for_quantity(p.cost_price_paisa, max(p.stock_quantity_milli, 0))
        )
        out.append(StockRow(p, names.get(p.category_id, "No category"), value, status))
    return out


@dataclass(frozen=True)
class CreditRow:
    customer: Customer
    balance: ledger.BalanceState
    overdue: ledger.OverdueStatus
    last_payment_at: datetime | None


def credit_rows(now: datetime | None = None) -> tuple[list[CreditRow], list[CreditRow]]:
    """(owing, oldest overdue first then largest; in credit)."""
    now = now or datetime.now(UTC)
    owing, credit = [], []
    for c in db.session.scalars(
        db.select(Customer).where(Customer.is_active.is_(True), Customer.balance_paisa != 0)
    ):
        entries = khata_service.entries_for(c.id)
        pays = [e.created_at for e in entries if e.entry_type == "payment"]
        row = CreditRow(
            c,
            ledger.describe_balance(c.balance_paisa),
            ledger.compute_overdue_status(entries, c.credit_terms_days, now),
            max(pays) if pays else None,
        )
        (owing if c.balance_paisa > 0 else credit).append(row)
    owing.sort(key=lambda r: (-r.overdue.days_overdue, -r.customer.balance_paisa))
    credit.sort(key=lambda r: r.customer.balance_paisa)
    return owing, credit


# --- the report document (screen = CSV = PDF) -------------------------------------------------


@dataclass
class Section:
    heading: str
    columns: list[str]
    rows: list[list]  # cells: str, int (paisa, when in money_cols), None
    money_cols: set[int] = field(default_factory=set)
    right_cols: set[int] = field(default_factory=set)  # e.g. percentages: numbers kept as text
    total: list | None = None
    empty_text: str = "Nothing in this period."


@dataclass
class ReportDoc:
    title: str
    period_label: str
    sections: list[Section]
    notes: list[str] = field(default_factory=list)
    summary: list[tuple[str, str]] = field(default_factory=list)


def rs(paisa: int | None) -> str:
    if paisa is None:
        return "—"
    return f"{'-' if paisa < 0 else ''}Rs {abs(paisa) // 100:,}"


def qty(milli: int, unit: str = "") -> str:
    whole = milli / 1000
    text = f"{int(whole)}" if milli % 1000 == 0 else f"{whole:g}"
    return f"{text} {unit}".strip()


def cell_text(section: Section, i: int, value) -> str:
    if value is None:
        return "—"
    if i in section.money_cols and isinstance(value, int):
        return rs(value)
    return str(value)


def to_csv(doc: ReportDoc) -> str:
    """Numbers as plain rupees for a spreadsheet (ADR-0034 §10): no 'Rs', no commas."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([doc.title, doc.period_label])
    for label, value in doc.summary:
        w.writerow([label, value])
    for s in doc.sections:
        w.writerow([])
        w.writerow([s.heading])
        w.writerow(s.columns)
        for row in [*s.rows, *([s.total] if s.total else [])]:
            w.writerow(
                [
                    ""
                    if v is None
                    else (v / 100 if i in s.money_cols and isinstance(v, int) else v)
                    for i, v in enumerate(row)
                ]
            )
    for n in doc.notes:
        w.writerow([])
        w.writerow([n])
    return buf.getvalue()


# --- the five reports -----------------------------------------------------------------------


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def sales_report(period: Period) -> ReportDoc:
    t = sales_totals(period)
    days = sales_by_day(period)
    return ReportDoc(
        title="Sales",
        period_label=period.label,
        summary=[
            ("Sales", str(t.count)),
            ("Gross sales", rs(t.gross_paisa)),
            ("Refunds approved", rs(t.refunds_paisa)),
            ("Net sales", rs(t.net_paisa)),
        ],
        sections=[
            Section(
                "By day",
                ["Date", "Sales", "Gross", "Refunds", "Net"],
                [[f"{d.day} {d:%b %Y}", n, g, r, g - r] for d, n, g, r in days],
                money_cols={2, 3, 4},
                total=["Total", t.count, t.gross_paisa, t.refunds_paisa, t.net_paisa]
                if days
                else None,
            ),
            # the table view behind the dashboard's busiest-hours chart (dataviz: relief for
            # the low-contrast context bars is visible labels *and* a table)
            Section(
                "By hour of day",
                ["Hour", "Sales", "Amount"],
                [[f"{h:02d}:00–{(h + 1) % 24:02d}:00", n, v] for h, n, v in sales_by_hour(period)],
                money_cols={2},
            ),
            Section(
                "By payment method",
                ["Method", "Sales"],
                [
                    [{"cash": "Cash", "card": "Card", "credit": "Khata"}.get(m, m), v]
                    for m, v in sorted(t.by_method.items())
                ],
                money_cols={1},
            ),
            Section(
                "By category",
                ["Category", "Sales"],
                [[n, v] for n, v in sales_by_category(period)],
                money_cols={1},
            ),
            Section(
                "Best sellers",
                ["Product", "Quantity", "Sales"],
                [[n, qty(q), v] for n, q, v in top_products(period)],
                money_cols={2},
            ),
        ],
    )


def profit_report(period: Period) -> ReportDoc:
    p = estimated_profit(period)
    rows = profit_by_category(period)
    return ReportDoc(
        title="Estimated profit",
        period_label=period.label,
        summary=[
            ("Net sales", rs(p.net_sales_paisa)),
            (
                "Sales with a known cost",
                f"{rs(p.covered_sales_paisa)} ({percent(p.coverage_percent)})",
            ),
            ("Estimated cost", rs(p.estimated_cost_paisa)),
            ("Estimated profit", rs(p.estimated_profit_paisa)),
            ("Margin", percent(p.margin_percent)),
        ],
        sections=[
            Section(
                "By category",
                [
                    "Category",
                    "Net sales",
                    "With known cost",
                    "Estimated cost",
                    "Estimated profit",
                    "Margin",
                ],
                [
                    [
                        n,
                        x.net_sales_paisa,
                        x.covered_sales_paisa,
                        x.estimated_cost_paisa,
                        x.estimated_profit_paisa,
                        percent(x.margin_percent),
                    ]
                    for n, x in rows
                ],
                money_cols={1, 2, 3, 4},
                right_cols={5},
            )
        ],
        notes=[
            "Estimated at today's cost prices: past periods change if cost prices change.",
            "Items without a cost price are left out of cost, profit and margin — never "
            "counted as free."
            + (
                f" This period: {rs(p.uncovered_sales_paisa)} of sales."
                if p.uncovered_sales_paisa
                else ""
            ),
        ],
    )


def inventory_report() -> ReportDoc:
    rows = stock_rows()
    known = [r for r in rows if r.value_paisa is not None]
    unknown = len(rows) - len(known)
    total = sum(r.value_paisa for r in known)
    return ReportDoc(
        title="Stock value",
        period_label=f"Now ({clock.format_shop_time(datetime.now(UTC))})",
        summary=[
            ("Products", str(len(rows))),
            ("Stock value at cost", rs(total)),
            ("Value unknown (no cost price)", str(unknown)),
        ],
        sections=[
            Section(
                "Products",
                ["Product", "Category", "In stock", "Cost price", "Value"],
                [
                    [
                        r.product.name,
                        r.category,
                        qty(r.product.stock_quantity_milli, r.product.unit_label),
                        r.product.cost_price_paisa,
                        r.value_paisa,
                    ]
                    for r in rows
                ],
                money_cols={3, 4},
                total=["Total", "", "", None, total] if rows else None,
                empty_text="No products yet.",
            )
        ],
        notes=[
            "Valued at cost price. A product without a cost price shows — and isn't "
            "counted at zero or at its selling price."
        ]
        if unknown
        else [],
    )


def low_stock_report() -> ReportDoc:
    rows = stock_rows()

    def section(heading, status, empty):
        return Section(
            heading,
            ["Product", "Category", "In stock", "Low-stock threshold"],
            [
                [
                    r.product.name,
                    r.category,
                    qty(r.product.stock_quantity_milli, r.product.unit_label),
                    qty(r.product.low_stock_threshold_milli, r.product.unit_label)
                    if r.product.low_stock_threshold_milli is not None
                    else None,
                ]
                for r in rows
                if r.status == status
            ],
            empty_text=empty,
        )

    return ReportDoc(
        title="Low stock",
        period_label=f"Now ({clock.format_shop_time(datetime.now(UTC))})",
        sections=[
            section("Out of stock — reorder now", "out", "Nothing is out of stock."),
            section("Running low", "low", "Nothing is running low."),
            section("Never counted", "never_counted", "Every product has been counted."),
        ],
        notes=[
            "Never counted: no delivery or count has ever been recorded, so Sukoon doesn't "
            "know how many there are. Not the same as out of stock."
        ],
    )


def credit_report(now: datetime | None = None) -> ReportDoc:
    owing, credit = credit_rows(now)
    total_owed = sum(r.balance.amount_paisa for r in owing)
    return ReportDoc(
        title="Outstanding credit",
        period_label=f"Now ({clock.format_shop_time(now or datetime.now(UTC))})",
        summary=[
            ("Customers owing", str(len(owing))),
            ("Total owed", rs(total_owed)),
            ("Customers in credit", str(len(credit))),
        ],
        sections=[
            Section(
                "Owing",
                ["Customer", "Phone", "Owes", "Overdue", "Last payment"],
                [
                    [
                        r.customer.name,
                        r.customer.phone_raw or "",
                        r.balance.amount_paisa,
                        f"{r.overdue.days_overdue} days" if r.overdue.is_overdue else "",
                        clock.format_shop_time(r.last_payment_at, "%d %b %Y")
                        if r.last_payment_at
                        else "Never",
                    ]
                    for r in owing
                ],
                money_cols={2},
                total=["Total", "", total_owed, "", ""] if owing else None,
                empty_text="Nobody owes anything.",
            ),
            Section(
                "In credit (the shop owes them)",
                ["Customer", "Phone", "In credit"],
                [
                    [r.customer.name, r.customer.phone_raw or "", r.balance.amount_paisa]
                    for r in credit
                ],
                money_cols={2},
                empty_text="Nobody is in credit.",
            ),
        ],
    )


REPORTS = {
    "sales": ("Sales", True),
    "profit": ("Estimated profit", True),
    "stock": ("Stock value", False),
    "low-stock": ("Low stock", False),
    "credit": ("Outstanding credit", False),
}


def build(kind: str, period: Period | None) -> ReportDoc:
    if kind == "sales":
        return sales_report(period)
    if kind == "profit":
        return profit_report(period)
    if kind == "stock":
        return inventory_report()
    if kind == "low-stock":
        return low_stock_report()
    if kind == "credit":
        return credit_report()
    raise KeyError(kind)


# --- PDF (A4), the same document as the screen and CSV ----------------------------------------


def to_pdf(
    doc: ReportDoc, *, shop_name: str = "Al-Rehman General Store", printed: str | None = None
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    teal, muted, ink = (0x0E / 255, 0x6B / 255, 0x57 / 255), (0.52, 0.52, 0.55), (0.11, 0.11, 0.12)
    buf = io.BytesIO()
    page_w, page_h = A4
    left, right = 16 * mm, page_w - 16 * mm
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{doc.title} — {doc.period_label}")
    printed = printed or clock.format_shop_time(datetime.now(UTC), "%d %b %Y %H:%M")
    page = 1

    def fit(text: str, font: str, size: float, width: float) -> str:
        if stringWidth(text, font, size) <= width:
            return text
        while text and stringWidth(text + "…", font, size) > width:
            text = text[:-1]
        return text + "…"

    def header() -> float:
        y = page_h - 18 * mm
        c.setFillColorRGB(*teal)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(left, y, shop_name)
        c.setFillColorRGB(*muted)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(right, y, f"{doc.title} · {doc.period_label}")
        c.drawRightString(right, y - 4.5 * mm, f"Printed {printed} · page {page}")
        return y - 14 * mm

    def new_page() -> float:
        nonlocal page
        c.showPage()
        page += 1
        return header()

    y = header()
    c.setFillColorRGB(*ink)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(left, y, doc.title)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*muted)
    c.drawString(left, y - 5.5 * mm, doc.period_label)
    y -= 14 * mm
    for label, value in doc.summary:
        c.setFillColorRGB(*muted)
        c.setFont("Helvetica", 9)
        c.drawString(left, y, label)
        c.setFillColorRGB(*ink)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(left + 110 * mm, y, value)
        y -= 5.5 * mm
    y -= 4 * mm

    for s in doc.sections:
        if y < 40 * mm:
            y = new_page()
        c.setFillColorRGB(*ink)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, s.heading)
        y -= 7 * mm
        width = (right - left) / max(len(s.columns), 1)
        first = width * 1.6 if len(s.columns) > 2 else width
        rest = (right - left - first) / max(len(s.columns) - 1, 1)
        xs = [left] + [left + first + rest * i for i in range(len(s.columns) - 1)]

        # a column is right-aligned as a whole — heading included — when it holds money, is
        # marked right, or its first row is a number (the first version decided per cell, so
        # a count column's heading sat left of its numbers)
        numeric_cols = (
            s.money_cols
            | s.right_cols
            | {i for i, v in enumerate(s.rows[0] if s.rows else []) if i > 0 and isinstance(v, int)}
        )

        # bound as defaults: called only within this loop pass, but say so explicitly
        def row(
            cells,
            *,
            bold=False,
            head=False,
            numeric_cols=numeric_cols,
            xs=xs,
            first=first,
            rest=rest,
        ):
            nonlocal y
            if y < 20 * mm:
                y = new_page()
            c.setFont("Helvetica-Bold" if (bold or head) else "Helvetica", 7.5 if head else 8.5)
            c.setFillColorRGB(*(muted if head else ink))
            two_lines = False
            for i, text in enumerate(cells):
                col_w = first if i == 0 else rest
                lines = [text]
                if head:
                    # headings wrap onto a second line rather than being cut off, measured in
                    # the heading's own font (the first version measured body text and cut)
                    font, size = "Helvetica-Bold", 7.5
                    if stringWidth(text, font, size) > col_w - 3 * mm and " " in text:
                        words = text.split()
                        split = max(1, len(words) // 2)
                        lines = [" ".join(words[:split]), " ".join(words[split:])]
                        two_lines = True
                    lines = [fit(line, font, size, col_w - 3 * mm) for line in lines]
                else:
                    lines = [fit(text, "Helvetica", 8.5, col_w - 3 * mm)]
                for n, line in enumerate(lines):
                    ly = y - n * 3.2 * mm
                    if i in numeric_cols:
                        c.drawRightString(xs[i] + col_w - 2 * mm, ly, line)
                    else:
                        c.drawString(xs[i], ly, line)
            y -= (9 if two_lines else 6) * mm

        row([col.upper() for col in s.columns], head=True)
        if not s.rows:
            c.setFont("Helvetica", 8.5)
            c.setFillColorRGB(*muted)
            c.drawString(left, y, s.empty_text)
            y -= 8 * mm
            continue
        for r in s.rows:
            row([cell_text(s, i, v) for i, v in enumerate(r)])
        if s.total:
            row(
                [cell_text(s, i, v) if v is not None else "" for i, v in enumerate(s.total)],
                bold=True,
            )
        y -= 4 * mm

    for n in doc.notes:
        if y < 20 * mm:
            y = new_page()
        c.setFillColorRGB(*muted)
        c.setFont("Helvetica", 7.5)
        c.drawString(left, y, fit(n, "Helvetica", 7.5, right - left))
        y -= 4.5 * mm
    c.showPage()
    c.save()
    return buf.getvalue()
