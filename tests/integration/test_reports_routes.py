"""Insights and report screens and exports (Phase 6; ADR-0034): Admin only, calm when
empty, and the exports match the screen."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from sukoon.extensions import db
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import sales_service
from sukoon.services.sales_service import CartLine
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

PAGES = ["/insights", "/insights?preset=week", "/insights?preset=month", "/reports",
         "/reports/sales", "/reports/profit", "/reports/stock", "/reports/low-stock",
         "/reports/credit", "/reports/sales.csv", "/reports/profit.pdf"]


def _as(client, login, who):
    client.post("/logout")
    login(*({"cashier": ("T1", CASHIER_PASSWORD), "admin": ("Owner", ADMIN_PASSWORD)}[who]))


@pytest.fixture
def sold(seeded):
    seed_invoice_counter()
    p = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000, cost_price_paisa=52_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=10_000,
                             reason="in", user_id=seeded["admin"].id)
    s = sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=2_000, unit_price_paisa=60_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id)
    return s


def test_cashiers_get_nothing_admins_get_everything(client, login, seeded):
    _as(client, login, "cashier")
    for page in PAGES:
        assert client.get(page).status_code == 403, page
    assert 'title="Insights"' not in client.get("/till/").get_data(as_text=True)
    _as(client, login, "admin")
    for page in PAGES:
        assert client.get(page).status_code == 200, page
    assert 'title="Insights"' in client.get("/till/").get_data(as_text=True)


def test_an_empty_shop_renders_calmly(client, login, seeded):
    _as(client, login, "admin")
    html = client.get("/insights").get_data(as_text=True)
    assert "No sales yet today." in html and "Nothing to compare with" in html
    assert "Nobody owes anything" in html
    assert "Nothing in this period." in client.get("/reports/sales").get_data(as_text=True)


def test_insights_shows_todays_sale_profit_and_the_chart(client, login, sold):
    _as(client, login, "admin")
    html = client.get("/insights").get_data(as_text=True)
    assert "Rs 1,200" in html  # today's sales
    assert "Rs 160" in html and "13.3% margin" in html and "At today's cost prices" in html
    assert "Busiest hours today" in html and "Peak:" in html
    assert "Walk-in customer" in html


def test_custom_dates_are_validated_on_screen(client, login, seeded):
    _as(client, login, "admin")
    resp = client.get("/reports/sales?from=2026-09-15&to=2026-09-14", follow_redirects=True)
    assert "The end date is before the start date." in resp.get_data(as_text=True)
    assert client.get("/reports/nonsense").status_code == 404


def test_exports_match_the_screen(client, login, sold):
    _as(client, login, "admin")
    today = (datetime.now(UTC) + timedelta(hours=5)).date().isoformat()
    args = f"from={today}&to={today}"
    html = client.get(f"/reports/sales?{args}").get_data(as_text=True)
    assert "Rs 1,200" in html
    resp = client.get(f"/reports/sales.csv?{args}")
    assert resp.mimetype == "text/csv" and "attachment" in resp.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert ["Net sales", "Rs 1,200"] in rows
    pdf = client.get(f"/reports/sales.pdf?{args}")
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF-")
    assert db.session.get(type(sold), sold.id)
