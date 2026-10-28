"""Route-level authorization for catalog & stock management (ADR-0019, ADR-0008)
plus the label-sheet endpoint and configurable geometry (ADR-0010)."""
from __future__ import annotations

import pytest

from sukoon.extensions import db
from sukoon.services import inventory_service as inv
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


@pytest.fixture
def product(app):
    return inv.create_product(name="Dalda 5L", sell_price_paisa=285000)


MANAGEMENT_ROUTES = [
    ("GET", "/stock/products/new"),
    ("POST", "/stock/products"),
    ("POST", "/stock/products/1"),
    ("POST", "/stock/products/1/delete"),
    ("POST", "/stock/products/1/adjust"),
    ("POST", "/stock/products/1/barcodes"),
    ("GET", "/stock/categories"),
    ("POST", "/stock/categories"),
    ("POST", "/stock/labels.pdf"),
]


@pytest.mark.parametrize("method,path", MANAGEMENT_ROUTES)
def test_cashier_is_forbidden_from_every_management_route(
    client, seeded, login, product, method, path
):
    login("T1", CASHIER_PASSWORD)
    resp = client.open(path, method=method)
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


def test_cashier_can_view_stock_and_product_detail(client, seeded, login, product):
    login("T1", CASHIER_PASSWORD)
    assert client.get("/stock/").status_code == 200
    assert client.get(f"/stock/products/{product.id}").status_code == 200


def test_admin_can_create_a_product(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(
        "/stock/products",
        data={"name": "Sunridge Atta 10kg", "sell_price": "1450", "unit_label": "bag"},
    )
    assert resp.status_code == 302
    rows, total = inv.list_products(query="Sunridge")
    assert total == 1 and rows[0].sku.startswith("GEN-")


def test_admin_can_adjust_stock_via_route(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(
        f"/stock/products/{product.id}/adjust",
        data={"movement_type": "stock_in", "quantity": "12", "reason": "PO-1"},
    )
    assert resp.status_code == 302
    db.session.expire_all()
    assert inv.get_product(product.id).stock_quantity_milli == 12000


def test_sell_price_change_requires_step_up(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    # no step-up password -> refused
    resp = client.post(
        f"/stock/products/{product.id}",
        data={"name": "Dalda 5L", "sell_price": "3000"},
    )
    assert resp.status_code == 403
    db.session.expire_all()
    assert inv.get_product(product.id).sell_price_paisa == 285000

    # correct step-up password -> applied
    resp = client.post(
        f"/stock/products/{product.id}",
        data={"name": "Dalda 5L", "sell_price": "3000", "step_up_password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 302
    db.session.expire_all()
    assert inv.get_product(product.id).sell_price_paisa == 300000


def test_non_price_edit_needs_no_step_up(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(
        f"/stock/products/{product.id}",
        data={"name": "Dalda Cooking Oil 5L", "sell_price": "2850"},
    )
    assert resp.status_code == 302
    db.session.expire_all()
    assert inv.get_product(product.id).name == "Dalda Cooking Oil 5L"


def test_price_override_barcode_requires_step_up(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(
        f"/stock/products/{product.id}/barcodes",
        data={"mode": "assign", "barcode": "OV-1", "price_override": "2000"},
    )
    assert resp.status_code == 403
    assert inv.resolve_barcode("OV-1") is None

    resp = client.post(
        f"/stock/products/{product.id}/barcodes",
        data={
            "mode": "assign", "barcode": "OV-1", "price_override": "2000",
            "step_up_password": ADMIN_PASSWORD,
        },
    )
    assert resp.status_code == 302
    assert inv.resolve_barcode("OV-1").unit_price_paisa == 200000


def test_label_sheet_endpoint_returns_a_pdf(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    row = inv.generate_barcode(product=product, user_id=seeded["admin"].id)
    resp = client.post("/stock/labels.pdf", data={"barcode_id": str(row.id)})
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:5] == b"%PDF-"


def test_list_needs_completing_filter(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    inv.create_product(name="Incomplete", sell_price_paisa=1000)  # provisional
    resp = client.get("/stock/?filter=needs_completing")
    assert resp.status_code == 200
    assert b"Incomplete" in resp.data


def test_admin_full_product_lifecycle_through_routes(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    # edit form renders
    p = inv.create_product(name="Temp", sell_price_paisa=100000)
    assert client.get(f"/stock/products/{p.id}/edit").status_code == 200
    # a validation error re-renders the form with 400 (price unchanged -> no step-up)
    bad = client.post(
        f"/stock/products/{p.id}", data={"name": "  ", "sell_price": "1000"}
    )
    assert bad.status_code == 400
    # generate an internal barcode via the route
    resp = client.post(
        f"/stock/products/{p.id}/barcodes", data={"mode": "generate"}
    )
    assert resp.status_code == 302
    assert inv.barcodes_for_product(p.id)[0].barcode.startswith("SK-")
    # delete (no history) -> hard delete, redirect to list
    resp = client.post(f"/stock/products/{p.id}/delete")
    assert resp.status_code == 302
    assert inv.get_product(p.id) is None


def test_admin_category_crud_through_routes(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    assert client.post("/stock/categories", data={"name": "Grains"}).status_code == 302
    cat = inv.list_categories()[0]
    assert cat.name == "Grains"
    resp = client.post(
        f"/stock/categories/{cat.id}", data={"name": "Grains & Flours", "display_order": "2"}
    )
    assert resp.status_code == 302
    db.session.expire_all()
    assert inv.list_categories()[0].name == "Grains & Flours"
    # duplicate name flashes an error, stays 302
    assert client.post("/stock/categories", data={"name": "Grains & Flours"}).status_code == 302


def test_adjust_stock_insufficient_is_flashed_not_500(client, seeded, login, product):
    login("Owner", ADMIN_PASSWORD)
    resp = client.post(
        f"/stock/products/{product.id}/adjust",
        data={"movement_type": "stock_out", "quantity": "5", "reason": "damage"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"in stock" in resp.data  # the InsufficientStockError message


def test_bulk_entry_commits_a_row(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    assert client.get("/stock/bulk").status_code == 200
    resp = client.post(
        "/stock/bulk",
        data={"barcode": "8964000555", "name": "Nestle Water 1.5L", "sell_price": "80"},
    )
    assert resp.status_code == 302
    match = inv.resolve_barcode("8964000555")
    assert match is not None and match.product.name == "Nestle Water 1.5L"


def test_bulk_entry_existing_code_jumps_to_product_not_duplicate(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    p = inv.create_product(name="Existing", sell_price_paisa=5000)
    inv.assign_barcode(product=p, code="DUP-BULK", user_id=seeded["admin"].id)
    before = inv.list_products()[1]
    resp = client.post(
        "/stock/bulk", data={"barcode": "DUP-BULK", "name": "Should Not Create", "sell_price": "9"}
    )
    assert resp.status_code == 302
    assert f"/stock/products/{p.id}" in resp.headers["Location"]
    assert inv.list_products()[1] == before  # nothing created


def test_bulk_entry_forbidden_for_cashier(client, seeded, login):
    login("T1", CASHIER_PASSWORD)
    assert client.get("/stock/bulk").status_code == 403
    assert client.post("/stock/bulk", data={"name": "x", "sell_price": "1"}).status_code == 403


def test_stock_list_formats_quantity_from_the_shared_column(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    bags = inv.create_product(name="Atta 10kg", sell_price_paisa=145000, unit_label="bag")
    loose = inv.create_product(
        name="Loose Sugar", sell_price_paisa=15000, allows_fractional=True, unit_label="kg"
    )
    inv.apply_stock_movement(
        product=bags, movement_type="stock_in", quantity_milli=42000,
        reason="in", user_id=seeded["admin"].id,
    )
    inv.apply_stock_movement(
        product=loose, movement_type="stock_in", quantity_milli=1500,
        reason="in", user_id=seeded["admin"].id,
    )
    body = client.get("/stock/").data
    assert b"42 bag" in body
    assert b"1.5 kg" in body


def test_label_geometry_is_configurable_via_settings(app):
    from sukoon.services import settings_service
    from sukoon.services.receipts import labels

    settings_service.set("label_sheet.columns", 4)
    settings_service.set("label_sheet.rows", 10)
    db.session.commit()
    geo = labels.load_geometry()
    assert (geo.columns, geo.rows, geo.per_page) == (4, 10, 40)


# --- paisa prices (ADR-0044) ---------------------------------------------------------------

def test_a_price_with_paisa_saves_and_a_third_decimal_is_a_message_not_a_500(
    client, seeded, login, product
):
    login("OW", ADMIN_PASSWORD)
    form = {"name": product.name, "sell_price": "2850", "cost_price": "4.30"}
    assert client.post(f"/stock/products/{product.id}", data=form).status_code == 302
    db.session.expire_all()
    assert inv.get_product(product.id).cost_price_paisa == 430

    resp = client.post(f"/stock/products/{product.id}",
                       data={**form, "cost_price": "4.305"})
    assert resp.status_code == 400
    assert "Use at most two decimals" in resp.get_data(as_text=True)

    resp = client.post(f"/stock/products/{product.id}/barcodes",
                       data={"barcode": "123", "price_override": "1.234"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert "Use at most two decimals" in resp.get_data(as_text=True)


def test_a_new_product_keeps_its_paisa_and_shows_them(client, seeded, login):
    login("OW", ADMIN_PASSWORD)
    resp = client.post("/stock/products", data={"name": "Biscuits", "sell_price": "105.50",
                                                "cost_price": "4.30"}, follow_redirects=True)
    page = resp.get_data(as_text=True)
    assert "Rs 105.50" in page
    p = inv.list_products(query="Biscuits")[0][0]
    assert (p.sell_price_paisa, p.cost_price_paisa) == (10550, 430)


def test_the_catalog_list_shows_cost_and_low_stock_level(client, seeded, login):
    cat = inv.create_category("Oil")
    inv.create_product(name="Sufi Oil 1L", sell_price_paisa=52_000, cost_price_paisa=50_940,
                       category=cat, low_stock_threshold_milli=3_000)
    inv.create_product(name="Mystery Item", sell_price_paisa=10_000)  # cost and level unset
    login("T1", CASHIER_PASSWORD)  # the list is open to cashiers, as product detail is
    page = client.get("/stock/").get_data(as_text=True)
    assert ">Cost<" in page and ">Low at<" in page
    sufi = page[page.index("Sufi Oil 1L"):]
    sufi = sufi[:sufi.index("</tr>")]
    assert "Rs 509.40" in sufi and "3 unit" in sufi and "Rs 520" in sufi
    mystery = page[page.index("Mystery Item"):]
    mystery = mystery[:mystery.index("</tr>")]
    assert "unknown" in mystery and "—" in mystery
