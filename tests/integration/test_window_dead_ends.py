"""Found by the developer testing the packaged window on Windows (2026-09-18).

The desktop window has no address bar and no Back button, so anything that navigates the window
somewhere it can't come back from traps the user until they close Sukoon itself. Two shapes of
that bug, both real:

* a PDF opened **in place** — the receipt after a sale, a Khata statement, a report;
* an **error page** with nothing to click — a label sheet with no barcode ticked showed one.

Every PDF is therefore a download, and every error page offers a way back.
"""
from __future__ import annotations

import pytest

from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import sales_service
from sukoon.services.sales_service import CartLine
from tests.conftest import ADMIN_PASSWORD


@pytest.fixture
def product(app):
    return inv.create_product(name="Dalda 5L", sell_price_paisa=285000)


@pytest.fixture
def sold(seeded):
    seed_invoice_counter()
    p = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000, cost_price_paisa=52_000)
    inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=10_000,
                             reason="in", user_id=seeded["admin"].id)
    return sales_service.record_sale(
        lines=[CartLine(product=p, quantity_milli=2_000, unit_price_paisa=60_000,
                        quantity_source="stepper")],
        payment_method="cash", user_id=seeded["cashier"].id)


@pytest.fixture
def usman(seeded):
    seed_invoice_counter()
    ghee = inv.create_product(name="Ghee 1kg", sell_price_paisa=60_000)
    inv.apply_stock_movement(product=ghee, movement_type="stock_in", quantity_milli=100_000,
                             reason="in", user_id=seeded["admin"].id)
    customer = khata.create_customer(name="Haji Muhammad Usman", phone_raw="0300 5541298",
                                     user_id=seeded["cashier"].id)
    sales_service.record_sale(
        lines=[CartLine(product=ghee, quantity_milli=2_000, unit_price_paisa=60_000,
                        quantity_source="stepper")],
        payment_method="credit", customer_id=customer.id, user_id=seeded["cashier"].id)
    return customer


def _disposition(response):
    return response.headers.get("Content-Disposition", "")


def test_a_receipt_downloads_instead_of_taking_over_the_window(client, seeded, login, sold):
    login("Owner", ADMIN_PASSWORD)
    sale_id = sold.id
    response = client.get(f"/till/receipt/{sale_id}.pdf")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert _disposition(response).startswith("attachment")


def test_a_khata_statement_downloads(client, seeded, login, usman):
    login("Owner", ADMIN_PASSWORD)
    response = client.get(f"/khata/{usman.id}/statement.pdf?period=2026-10")
    assert response.status_code == 200 and _disposition(response).startswith("attachment")


def test_a_report_pdf_downloads(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    response = client.get("/reports/sales.pdf")
    assert response.status_code == 200 and _disposition(response).startswith("attachment")


def test_a_label_sheet_downloads(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    row = inv.generate_barcode(product=product, user_id=seeded["admin"].id)
    response = client.post("/stock/labels.pdf", data={"barcode_id": str(row.id)})
    assert response.status_code == 200 and _disposition(response).startswith("attachment")


def test_no_pdf_link_opens_a_new_window(client, seeded, login, usman):
    """A new window means the system browser, which has no Sukoon session: the owner was asked to
    sign in again just to reach a statement."""
    login("Owner", ADMIN_PASSWORD)
    for path in (f"/khata/{usman.id}/statement", "/reports/sales"):
        assert b'target="_blank"' not in client.get(path).data, path


def test_a_label_sheet_with_nothing_ticked_comes_back_with_a_message(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    response = client.post("/stock/labels.pdf", data={}, headers={"Referer": "/stock/"},
                           follow_redirects=True)
    assert response.status_code == 200
    assert b"Tick at least one barcode" in response.data
    assert b"Stock" in response.data  # a real screen, not a dead end


@pytest.mark.parametrize("path,expected", [("/stock/products/999999", 404), ("/no-such-page", 404)])
def test_an_error_page_offers_a_way_back(client, seeded, login, path, expected):
    login("Owner", ADMIN_PASSWORD)
    response = client.get(path)
    assert response.status_code == expected
    assert b"Back to Sukoon" in response.data and b'href="/"' in response.data
    assert b"Nothing was saved" in response.data


def test_a_cashier_refused_a_screen_can_get_back(client, seeded, login):
    from tests.conftest import CASHIER_PASSWORD

    login("T1", CASHIER_PASSWORD)
    response = client.get("/insights")
    assert response.status_code == 403
    assert b"Back to Sukoon" in response.data and b"An Admin can" in response.data


def test_the_window_allows_downloads_and_keeps_links_inside_itself():
    from sukoon import desktop

    assert desktop.WEBVIEW_SETTINGS["ALLOW_DOWNLOADS"] is True
    assert desktop.WEBVIEW_SETTINGS["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False
