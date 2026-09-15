"""Reports against a hand-calculated scenario (Development Spec Phase 6 DoD: "every report
type verified against known seeded data with hand-checkable expected totals"; ADR-0034).

Scenario (shop time, Asia/Karachi = UTC+5):
  Mon 14 Sep 10:15  cash    Ghee x2 (1,200) + Soap x1 (280)                 = 1,480
  Mon 14 Sep 18:40  Khata   Oil x3 (1,770) + Biscuits x2 (160, no cost)      = 1,930
  Tue 15 Sep 00:30  card    Atta 1.5 kg (255)   <- 19:30 UTC on MONDAY        =   255
  Tue 15 Sep 19:05  cash    Soap x3 (840) + Biscuits x1 (80)                 =   920
  Tue 15 Sep 12:00  refund  Ghee x1 restocked (600)
  Tue 15 Sep 20:00  refund  Soap x1 damaged, not restocked (280)
Costs: Ghee 520, Oil 500, Soap 200, Atta 140/kg, Biscuits unknown.
  gross 4,585 · refunds 880 · net 3,705
  covered sales 4,345 - 880 = 3,465 · uncovered 240 (biscuits)
  cost 1,040 + 200 + 1,500 + 210 + 600 = 3,550, less the restocked ghee 520 = 3,030
  estimated profit 3,465 - 3,030 = 435 · margin 12.6% · coverage 93.5%
"""

from __future__ import annotations

import csv
import io
import time
from datetime import UTC, datetime, timedelta

import pytest

from sukoon.extensions import db
from sukoon.models import CreditLedgerEntry, Refund, Sale, SaleItem
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import money, refund_service, sales_service
from sukoon.services import reporting_service as rpt
from sukoon.services.refund_service import RefundLineSpec
from sukoon.services.sales_service import CartLine


def pk(d, h, m=0):
    """A Pakistan-time wall clock on September 2026 day ``d`` as a UTC instant."""
    return datetime(2026, 9, d, h, m, tzinfo=UTC) - timedelta(hours=5)


NOW = pk(15, 20, 30)


@pytest.fixture
def shop(seeded):
    seed_invoice_counter()
    admin, cashier = seeded["admin"], seeded["cashier"]
    groceries, household = inv.create_category("Groceries"), inv.create_category("Household")

    def product(name, sell, cost, cat, stock, **kw):
        p = inv.create_product(
            name=name,
            sell_price_paisa=sell * 100,
            category=cat,
            cost_price_paisa=cost * 100 if cost is not None else None,
            **kw,
        )
        if stock:
            inv.apply_stock_movement(
                product=p,
                movement_type="stock_in",
                quantity_milli=stock,
                reason="delivery",
                user_id=admin.id,
            )
        return p

    ghee = product("Ghee 1kg", 600, 520, groceries, 10_000)
    oil = product("Cooking Oil 1L", 590, 500, groceries, 10_000)
    soap = product("Soap", 280, 200, household, 10_000, low_stock_threshold_milli=6_000)
    atta = product(
        "Atta (loose)", 170, 140, groceries, 20_000, allows_fractional=True, unit_label="kg"
    )
    biscuits = product("Local Biscuits", 80, None, None, 0)  # never counted, cost unknown
    sugar = product("Sugar 1kg", 300, 250, groceries, 5_000)
    inv.apply_stock_movement(
        product=sugar,
        movement_type="stock_out",
        quantity_milli=5_000,
        reason="spilt",
        user_id=admin.id,
    )
    usman = khata.create_customer(name="Haji Usman", phone_raw="0300 5541298", user_id=cashier.id)
    khata.set_credit_terms(usman, credit_limit_paisa=None, credit_terms_days=10)

    def sell(when, method, *lines, customer=None):
        s = sales_service.record_sale(
            lines=[
                CartLine(
                    product=p,
                    quantity_milli=q,
                    unit_price_paisa=p.sell_price_paisa,
                    quantity_source="manual_weight" if p.allows_fractional else "stepper",
                )
                for p, q in lines
            ],
            payment_method=method,
            user_id=cashier.id,
            now=when,
            customer_id=customer.id if customer else None,
        )
        s.created_at = when
        for e in db.session.scalars(
            db.select(CreditLedgerEntry).where(CreditLedgerEntry.sale_id == s.id)
        ):
            e.created_at = when
        db.session.commit()
        return s

    s1 = sell(pk(14, 10, 15), "cash", (ghee, 2_000), (soap, 1_000))
    sell(pk(14, 18, 40), "credit", (oil, 3_000), (biscuits, 2_000), customer=usman)
    s3 = sell(pk(15, 0, 30), "card", (atta, 1_500))
    s4 = sell(pk(15, 19, 5), "cash", (soap, 3_000), (biscuits, 1_000))

    def refund(sale, product, q, restock, when):
        item = next(i for i in sale.items if i.product_id == product.id)
        r = refund_service.initiate_refund(
            sale_id=sale.id,
            reason="returned",
            initiated_by_user_id=cashier.id,
            lines=[RefundLineSpec(sale_item_id=item.id, quantity_milli=q, restock=restock)],
        )
        refund_service.approve_refund(refund_id=r.id, approved_by_user_id=admin.id)
        r.resolved_at = when
        db.session.commit()

    refund(s1, ghee, 1_000, True, pk(15, 12))
    refund(s4, soap, 1_000, False, pk(15, 20))
    return {
        "usman": usman,
        "s3": s3,
        "ghee": ghee,
        "soap": soap,
        "biscuits": biscuits,
        "sugar": sugar,
        **seeded,
    }


SEPT_14_15 = ("2026-09-14", "2026-09-15")


# --- periods (ADR-0034 §3–4) ---------------------------------------------------------------


def test_presets_are_shop_time_calendar_ranges_with_monday_weeks(app):
    today, week, month = (rpt.preset(n, now=NOW) for n in ("today", "week", "month"))
    assert (today.start, today.end) == (pk(15, 0), pk(16, 0))
    assert (week.start, week.end) == (pk(14, 0), pk(21, 0))  # Monday 14 to Monday 21
    assert month.start == pk(1, 0) and month.end == datetime(2026, 9, 30, 19, 0, tzinfo=UTC)


def test_custom_periods_are_inclusive_dates_and_validated(app):
    p = rpt.custom(*SEPT_14_15)
    assert (p.start, p.end) == (pk(14, 0), pk(16, 0))
    with pytest.raises(rpt.PeriodError, match="before the start"):
        rpt.custom("2026-09-15", "2026-09-14")
    with pytest.raises(rpt.PeriodError, match="both dates"):
        rpt.custom("", "2026-09-14")


def test_comparison_is_the_same_point_last_period(app):
    today = rpt.preset("today", now=NOW)
    c = rpt.comparison(today, now=NOW)
    assert (c.start, c.end) == (pk(8, 0), pk(8, 20, 30))  # same weekday, up to the same time
    custom = rpt.custom(*SEPT_14_15)
    c = rpt.comparison(custom)
    assert (c.start, c.end) == (pk(12, 0), pk(14, 0))


# --- sales --------------------------------------------------------------------------------


def test_sales_totals_match_the_hand_calculation(shop):
    t = rpt.sales_totals(rpt.custom(*SEPT_14_15))
    assert (t.count, t.gross_paisa, t.refunds_paisa, t.net_paisa) == (4, 458_500, 88_000, 370_500)
    assert t.by_method == {"cash": 240_000, "credit": 193_000, "card": 25_500}


def test_a_sale_at_half_past_midnight_belongs_to_the_shops_new_day(shop):
    # 00:30 Tuesday in Pakistan is 19:30 Monday UTC
    assert shop["s3"].created_at.hour == 19
    days = rpt.sales_by_day(rpt.custom(*SEPT_14_15))
    assert [(d.day, n, g, r) for d, n, g, r in days] == [
        (14, 2, 341_000, 0),
        (15, 2, 117_500, 88_000),
    ]
    assert rpt.sales_totals(rpt.preset("today", now=NOW)).count == 2


def test_busiest_hours_and_categories_and_best_sellers(shop):
    assert rpt.sales_by_hour(rpt.preset("today", now=NOW)) == [(0, 1, 25_500), (19, 1, 92_000)]
    assert rpt.sales_by_category(rpt.custom(*SEPT_14_15)) == [
        ("Groceries", 322_500),
        ("Household", 112_000),
        ("No category", 24_000),
    ]
    top = rpt.top_products(rpt.custom(*SEPT_14_15), limit=2)
    assert top == [("Cooking Oil 1L", 3_000, 177_000), ("Ghee 1kg", 2_000, 120_000)]


# --- estimated profit (ADR-0034 §2, §6) -----------------------------------------------------


def test_estimated_profit_matches_the_hand_calculation(shop):
    p = rpt.estimated_profit(rpt.custom(*SEPT_14_15))
    assert (p.net_sales_paisa, p.covered_sales_paisa, p.uncovered_sales_paisa) == (
        370_500,
        346_500,
        24_000,
    )
    assert (p.estimated_cost_paisa, p.estimated_profit_paisa) == (303_000, 43_500)
    assert rpt.percent(p.margin_percent) == "12.6%" and rpt.percent(p.coverage_percent) == "93.5%"


def test_profit_by_category_adds_up_and_unknown_cost_has_no_margin(shop):
    rows = dict(rpt.profit_by_category(rpt.custom(*SEPT_14_15)))
    assert (
        rows["Groceries"].net_sales_paisa,
        rows["Groceries"].estimated_cost_paisa,
        rows["Groceries"].estimated_profit_paisa,
    ) == (262_500, 223_000, 39_500)
    assert rows["Household"].estimated_profit_paisa == 4_000  # the damaged soap's cost stays
    assert (
        rows["No category"].covered_sales_paisa == 0 and rows["No category"].margin_percent is None
    )
    assert sum(r.estimated_profit_paisa for r in rows.values()) == 43_500


def test_sql_cost_rounding_is_exactly_the_money_rule(app, seeded):
    # the SQL half-up must agree with money.line_total_for_quantity, including .5 boundaries
    seed_invoice_counter()
    # costs are whole rupees (ADR-0007); fractional weights reach the .5 boundaries:
    # Rs 123 x 1.5 = 184.5 -> 185, Rs 1 x 0.5 = 0.5 -> 1, Rs 51 x 2.5 = 127.5 -> 128
    cases = [
        (12_300, 1_500),
        (14_000, 1_500),
        (9_900, 333),
        (100, 500),
        (33_300, 1_001),
        (19_900, 2_513),
        (5_100, 2_500),
    ]
    for cost, q in cases:
        p = inv.create_product(
            name=f"P{cost}-{q}",
            sell_price_paisa=100_000,
            cost_price_paisa=cost,
            allows_fractional=True,
            unit_label="kg",
        )
        inv.apply_stock_movement(
            product=p,
            movement_type="stock_in",
            quantity_milli=10_000,
            reason="in",
            user_id=seeded["admin"].id,
        )
        s = sales_service.record_sale(
            lines=[
                CartLine(
                    product=p,
                    quantity_milli=q,
                    unit_price_paisa=100_000,
                    quantity_source="manual_weight",
                )
            ],
            payment_method="cash",
            user_id=seeded["cashier"].id,
            now=NOW,
        )
        s.created_at = NOW
        db.session.commit()
        expected = money.line_total_for_quantity(cost, q)
        got = rpt.estimated_profit(rpt.preset("today", now=NOW)).estimated_cost_paisa
        assert got == expected, (cost, q)
        db.session.delete(s.items[0])
        db.session.delete(s)
        db.session.commit()


def test_an_empty_period_is_calm_not_an_error(shop):
    empty = rpt.custom("2026-08-01", "2026-08-02")
    p = rpt.estimated_profit(empty)
    assert p.net_sales_paisa == 0 and p.margin_percent is None and p.coverage_percent is None
    for kind in ("sales", "profit"):
        doc = rpt.build(kind, empty)
        assert all(not s.rows for s in doc.sections)
        assert rpt.to_csv(doc).startswith(f"{doc.title},")


# --- point-in-time reports ---------------------------------------------------------------


def test_stock_value_excludes_and_counts_unknown_cost(shop):
    doc = rpt.inventory_report()
    assert dict(doc.summary)["Stock value at cost"] == "Rs 11,970"  # 4,680 + 3,500 + 1,200 + 2,590
    assert dict(doc.summary)["Value unknown (no cost price)"] == "1"
    biscuits = next(r for r in doc.sections[0].rows if r[0] == "Local Biscuits")
    assert biscuits[4] is None and rpt.cell_text(doc.sections[0], 4, None) == "—"
    assert inv.catalog_summary()["stock_value_paisa"] == 1_197_000  # the Stock tile agrees


def test_low_stock_separates_out_low_and_never_counted(shop):
    doc = rpt.low_stock_report()
    names = {s.heading: [r[0] for r in s.rows] for s in doc.sections}
    assert names["Out of stock — reorder now"] == ["Sugar 1kg"]
    assert names["Running low"] == ["Soap"]  # 6 left, threshold 6
    assert names["Never counted"] == ["Local Biscuits"]


def test_credit_lists_owing_oldest_overdue_first_and_credit_separately(shop):
    usman = shop["usman"]
    other = khata.create_customer(name="In Credit", phone_raw=None, user_id=shop["cashier"].id)
    khata.record_payment(
        customer_id=other.id,
        amount_paisa=50_000,
        method="cash",
        received_by_user_id=shop["cashier"].id,
        allow_overpayment=True,
    )
    # 18:40 on the 14th to 12:00 on the 30th is 15 whole days; terms 10 -> 5 days overdue.
    # (The first version of this test said 16 and 6 — a hand-calculation slip, not the app.)
    doc = rpt.credit_report(now=pk(30, 12))
    owing, credit = doc.sections
    assert owing.rows == [["Haji Usman", "0300 5541298", 193_000, "5 days", "Never"]]
    assert owing.total == ["Total", "", 193_000, "", ""]
    assert credit.rows == [["In Credit", "", 50_000]]
    assert usman.id


# --- exports ---------------------------------------------------------------------------


def test_csv_totals_equal_the_screen_totals(shop):
    doc = rpt.sales_report(rpt.custom(*SEPT_14_15))
    rows = list(csv.reader(io.StringIO(rpt.to_csv(doc))))
    assert ["Net sales", "Rs 3,705"] in rows
    total = next(r for r in rows if r and r[0] == "Total")
    assert total == ["Total", "4", "4585.0", "880.0", "3705.0"]  # plain rupees for a spreadsheet


# --- performance (Development Spec Phase 6 required test) --------------------------------


@pytest.mark.slow
def test_reports_stay_fast_on_ten_thousand_sales(app, seeded):
    seed_invoice_counter()
    p = inv.create_product(name="Bulk", sell_price_paisa=10_000, cost_price_paisa=8_000)
    start = pk(1, 9)
    sales = [
        {
            "invoice_number": f"INV-2026-{i:05d}",
            "user_id": seeded["cashier"].id,
            "subtotal_paisa": 20_000,
            "discount_paisa": 0,
            "tax_paisa": 0,
            "total_paisa": 20_000,
            "payment_method": "cash",
            "status": "completed",
            "created_at": (start + timedelta(minutes=4 * i)).replace(tzinfo=None),
        }
        for i in range(10_000)
    ]
    db.session.execute(db.insert(Sale), sales)
    ids = db.session.scalars(db.select(Sale.id)).all()
    db.session.execute(
        db.insert(SaleItem),
        [
            {
                "sale_id": sid,
                "product_id": p.id,
                "product_name_snapshot": "Bulk",
                "unit_price_paisa_snapshot": 10_000,
                "quantity_milli": 2_000,
                "quantity_source": "stepper",
                "line_discount_paisa": 0,
                "line_total_paisa": 20_000,
            }
            for sid in ids
        ],
    )
    db.session.commit()
    month = rpt.preset("month", now=pk(29, 12))
    timings = {}
    for kind in ("sales", "profit"):
        t0 = time.perf_counter()
        doc = rpt.build(kind, month)
        timings[kind] = time.perf_counter() - t0
        assert doc.sections
    t0 = time.perf_counter()
    rpt.sales_by_hour(month)
    timings["hours"] = time.perf_counter() - t0
    p_ = rpt.estimated_profit(month)
    assert p_.net_sales_paisa == 10_000 * 20_000 and p_.estimated_cost_paisa == 10_000 * 16_000
    print("\nTIMINGS", {k: round(v, 3) for k, v in timings.items()})
    # 3.6 s before the zone was resolved once per report; ~0.2 s after.
    # A 1 s budget catches that kind of regression.
    assert all(t < 1.0 for t in timings.values()), timings
    assert Refund  # imported for the scenario fixture


def test_no_report_speaks_in_internal_jargon(shop):
    period = rpt.custom(*SEPT_14_15)
    for kind in rpt.REPORTS:
        doc = rpt.build(kind, period)
        text = " ".join(
            [
                doc.title,
                doc.period_label,
                *doc.notes,
                *(s.heading for s in doc.sections),
                *(s.empty_text for s in doc.sections),
            ]
        )
        assert "ADR" not in text and "paisa" not in text.lower(), kind
