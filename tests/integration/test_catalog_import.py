"""Importing a product spreadsheet, end to end (ADR-0043): staging, the owner's decisions,
Add to stock, the barcode worklist, undo, and who may do it."""
from __future__ import annotations

import io

import pytest

from sukoon.extensions import db
from sukoon.models import CatalogImportRow, Category, Product, ProductBarcode
from sukoon.services import catalog_import_service as imp
from sukoon.services import inventory_service as inv
from sukoon.services.money import rupees_input_value
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

FILE = """Name,Category,Cost Price,Selling Price,Low Stock Level
Sufi Oil 1L,Oil,509.4,520,2
Lux Soap,Soap,,110,1
Ghee 1kg,Ghee,900,1000,1
ghee 1KG,Ghee,950,1050,1
Tapal 95g,Tea,177,190,1
Tapal 95g,Tea,177,190,1
Mango Jam,Jam,140,,1
Odd One,Food,300,250,1
"""


def _import(staff, text=FILE):
    return imp.create_import(filename="shop.csv", data=text.encode(),
                             user_id=staff["admin"].id)


def _row(batch, name):
    return next(r for r in batch.rows if r.name == name)


def _products():
    return {p.name: p for p in db.session.scalars(db.select(Product))}


# --- staging (§2) -------------------------------------------------------------------------

def test_an_upload_stages_rows_and_makes_no_products(seeded):
    batch = _import(seeded)
    assert len(batch.rows) == 8
    assert db.session.query(Product).count() == 0
    assert imp.compute_summary(batch) == {
        "total": 8, "ready": 4, "choose_rows": 2, "choose_groups": 1, "needs_price": 1,
        "skipped": 1, "imported": 0}


def test_add_to_stock_makes_products_from_ready_rows_only(seeded):
    batch = _import(seeded)
    assert imp.add_ready_to_stock(batch, user_id=seeded["admin"].id) == 4
    products = _products()
    assert set(products) == {"Sufi Oil 1L", "Lux Soap", "Tapal 95g", "Odd One"}
    oil = products["Sufi Oil 1L"]
    assert (oil.cost_price_paisa, oil.sell_price_paisa, oil.low_stock_threshold_milli,
            oil.stock_quantity_milli, oil.category.name) == (50940, 52000, 2000, 0, "Oil")
    assert oil.sku.startswith("OIL-") and not oil.is_provisional
    assert all(not p.barcodes for p in products.values())


def test_skus_continue_the_shops_own_numbering(seeded):
    before = inv.create_product(name="Already here", sell_price_paisa=100)
    batch = _import(seeded)
    imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    after = inv.create_product(name="Added later", sell_price_paisa=100)
    numbers = sorted(int(p.sku.split("-")[1]) for p in _products().values())
    assert numbers == list(range(1, 7))
    assert int(before.sku[-4:]) == 1 and int(after.sku[-4:]) == 6


def test_an_existing_category_is_reused_ignoring_case(seeded):
    inv.create_category("oil")
    imp.add_ready_to_stock(_import(seeded), user_id=seeded["admin"].id)
    assert [c.name for c in db.session.scalars(db.select(Category)).all()
            if c.name.lower() == "oil"] == ["oil"]


def test_missing_cost_or_cost_above_price_imports_as_needs_completing(seeded):
    imp.add_ready_to_stock(_import(seeded), user_id=seeded["admin"].id)
    p = _products()
    assert p["Lux Soap"].is_provisional and p["Lux Soap"].cost_price_paisa is None
    assert p["Odd One"].is_provisional  # every field filled, but the cost is above the price


def test_add_to_stock_is_all_or_nothing(seeded, monkeypatch):
    batch = _import(seeded)
    calls = []
    real = imp.compute_cost_above_price

    def boom(row):
        calls.append(row)
        if len(calls) == 3:
            raise RuntimeError("disk full")
        return real(row)

    monkeypatch.setattr(imp, "compute_cost_above_price", boom)
    with pytest.raises(RuntimeError):
        imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    assert db.session.query(Product).count() == 0
    assert imp.compute_summary(imp.get_import(batch.id))["ready"] == 4


# --- the owner's decisions ------------------------------------------------------------------

def test_a_differing_group_waits_until_chosen_then_adds_later(seeded):
    batch = _import(seeded)
    imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    assert "Ghee 1kg" not in _products()
    second = _row(batch, "ghee 1KG")
    imp.choose_from_group(batch, "ghee 1kg", {second.id})
    first = _row(batch, "Ghee 1kg")
    assert first.status == "skipped"
    assert first.skip_reason == f"Not kept — you kept line {second.line_no}"
    assert imp.add_ready_to_stock(batch, user_id=seeded["admin"].id) == 1
    assert _products()["ghee 1KG"].sell_price_paisa == 105000


def test_a_group_can_be_decided_only_once(seeded):
    batch = _import(seeded)
    imp.choose_from_group(batch, "ghee 1kg", set())
    with pytest.raises(inv.ValidationError):
        imp.choose_from_group(batch, "ghee 1kg", set())


def test_a_row_without_a_price_is_added_once_priced(seeded):
    batch = _import(seeded)
    jam = _row(batch, "Mango Jam")
    for bad in (None, 0, -100):
        with pytest.raises(inv.ValidationError):
            imp.set_row_price(jam, bad)
    imp.set_row_price(jam, 15050)  # paisa allowed (ADR-0044)
    imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    assert _products()["Mango Jam"].sell_price_paisa == 15050


def test_skip_and_bring_back(seeded):
    batch = _import(seeded)
    oil = _row(batch, "Sufi Oil 1L")
    imp.skip_row(oil)
    assert oil.status == "skipped"
    imp.restore_row(oil)
    assert oil.status == "ready"


# --- undo (§5) ---------------------------------------------------------------------------

def test_undo_removes_unused_products_and_deactivates_used_ones(seeded):
    batch = _import(seeded)
    imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    p = _products()
    inv.assign_barcode(product=p["Lux Soap"], code="8961000000001", user_id=seeded["admin"].id)
    inv.apply_stock_movement(product=p["Tapal 95g"], movement_type="stock_in",
                             quantity_milli=5000, reason="count", user_id=seeded["admin"].id)
    assert imp.undo_import(batch) == (3, 1)
    left = _products()
    assert set(left) == {"Tapal 95g"} and not left["Tapal 95g"].is_active
    assert db.session.query(ProductBarcode).count() == 0
    summary = imp.compute_summary(imp.get_import(batch.id))
    assert (summary["imported"], summary["ready"]) == (1, 3)


# --- the screens -------------------------------------------------------------------------

@pytest.fixture
def admin(client, login, seeded):
    login("OW", ADMIN_PASSWORD)
    return seeded


def _upload(client, text=FILE, name="shop.csv"):
    return client.post("/stock/import/", data={"file": (io.BytesIO(text.encode()), name)},
                       content_type="multipart/form-data")


def test_upload_review_add_and_worklist_through_the_screens(client, admin):
    resp = _upload(client)
    assert resp.status_code == 302 and "/stock/import/1" in resp.headers["Location"]
    page = client.get("/stock/import/1").get_data(as_text=True)
    assert "Choose which to keep" in page and "Need a selling price" in page
    assert "Same as line 6" in page and "Add 4 to stock" in page

    resp = client.post("/stock/import/1/add")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/stock/import/1/products")
    page = client.get("/stock/import/1/products").get_data(as_text=True)
    assert "Sufi Oil 1L" in page and 'value="509.40"' in page and "cost above price" in page


def test_a_file_that_is_not_a_product_list_is_refused_on_screen(client, admin):
    resp = _upload(client, "Barcode,Item\n123,x\n")
    assert resp.status_code == 302
    page = client.get("/stock/import/").get_data(as_text=True)
    assert "doesn&#39;t look like a Sukoon product file" in page or "look like a Sukoon" in page


def test_an_unticked_group_is_not_skipped_by_accident(client, admin):
    _upload(client)
    client.post("/stock/import/1/choose", data={"group": "ghee 1kg"})
    assert all(r.status == "choose" for r in db.session.scalars(
        db.select(CatalogImportRow).where(CatalogImportRow.group_key == "ghee 1kg")))
    client.post("/stock/import/1/choose", data={"group": "ghee 1kg", "skip_all": "1"})
    assert all(r.status == "skipped" for r in db.session.scalars(
        db.select(CatalogImportRow).where(CatalogImportRow.group_key == "ghee 1kg")))


def _ready(client):
    _upload(client)
    client.post("/stock/import/1/add")
    return _products()


def _save(client, p, **over):
    form = {"name": p.name, "category_id": str(p.category_id or ""),
            "cost_price": rupees_input_value(p.cost_price_paisa),
            "sell_price": rupees_input_value(p.sell_price_paisa),
            "low_stock_threshold": str((p.low_stock_threshold_milli or 0) // 1000),
            "barcode": ""}
    form.update(over)
    return client.post(f"/stock/import/1/products/{p.id}?show=no_barcode", data=form,
                       follow_redirects=True)


def test_scanning_a_barcode_on_attaches_it_and_the_row_leaves_the_list(client, admin):
    oil = _ready(client)["Sufi Oil 1L"]
    page = _save(client, oil, barcode=" 8961008208016 ").get_data(as_text=True)
    assert "barcode 8961008208016 attached" in page
    assert inv.resolve_barcode("8961008208016").product.id == oil.id
    assert 'id="p%d"' % oil.id not in page  # done: it left "No barcode yet"
    assert imp.compute_worklist_counts(imp.get_import(1))["no_barcode"] == 3


def test_a_barcode_on_another_product_is_refused_and_nothing_changes(client, admin):
    p = _ready(client)
    inv.assign_barcode(product=p["Lux Soap"], code="111", user_id=admin["admin"].id)
    page = _save(client, p["Sufi Oil 1L"], barcode="111", cost_price="400").get_data(as_text=True)
    assert "Barcode 111 already belongs to Lux Soap." in page
    db.session.expire_all()
    assert db.session.get(Product, p["Sufi Oil 1L"].id).cost_price_paisa == 50940


def test_cost_category_and_level_save_without_a_password(client, admin):
    p = _ready(client)
    soap = p["Lux Soap"]
    _save(client, soap, cost_price="95", low_stock_threshold="4")
    db.session.expire_all()
    soap = db.session.get(Product, soap.id)
    assert (soap.cost_price_paisa, soap.low_stock_threshold_milli) == (9500, 4000)
    assert not soap.is_provisional  # completing it is an ordinary edit (ADR-0011)


def test_a_changed_price_needs_the_password(client, admin):
    oil = _ready(client)["Sufi Oil 1L"]
    page = _save(client, oil, sell_price="530").get_data(as_text=True)
    assert "needs your password. Nothing was saved." in page
    db.session.expire_all()
    assert db.session.get(Product, oil.id).sell_price_paisa == 52000
    _save(client, oil, sell_price="530", step_up_password=ADMIN_PASSWORD)
    db.session.expire_all()
    assert db.session.get(Product, oil.id).sell_price_paisa == 53000


def test_search_finds_a_product_in_the_worklist(client, admin):
    _ready(client)
    page = client.get("/stock/import/1/products?q=sufi").get_data(as_text=True)
    assert "Sufi Oil 1L" in page and "Lux Soap" not in page


def test_undo_through_the_screen(client, admin):
    _ready(client)
    page = client.post("/stock/import/1/undo", follow_redirects=True).get_data(as_text=True)
    assert "Undone: 4 products removed." in page
    assert db.session.query(Product).count() == 0


IMPORT_ROUTES = [
    ("GET", "/stock/import/"), ("POST", "/stock/import/"), ("GET", "/stock/import/1"),
    ("POST", "/stock/import/1/choose"), ("POST", "/stock/import/1/rows/1/skip"),
    ("POST", "/stock/import/1/add"), ("POST", "/stock/import/1/undo"),
    ("GET", "/stock/import/1/products"), ("POST", "/stock/import/1/products/1"),
]


@pytest.mark.parametrize("method,path", IMPORT_ROUTES)
def test_a_cashier_may_not_import(client, seeded, login, method, path):
    _import(seeded)
    login("T1", CASHIER_PASSWORD)
    assert client.open(path, method=method).status_code == 403


def test_the_real_shop_file_imports(seeded):
    """The cleaned spreadsheet in the repository goes all the way through."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "import" / "sukoon-products-import.csv"
    if not path.exists():
        pytest.skip("the shop's prepared file isn't in this checkout")
    batch = imp.create_import(filename=path.name, data=path.read_bytes(),
                              user_id=seeded["admin"].id)
    summary = imp.compute_summary(batch)
    assert summary["total"] > 8000 and summary["ready"] > 7000
    added = imp.add_ready_to_stock(batch, user_id=seeded["admin"].id)
    assert db.session.query(Product).count() == added
    products = list(db.session.scalars(db.select(Product)))
    assert all(p.sell_price_paisa > 0 and (p.cost_price_paisa is None or p.cost_price_paisa > 0)
               for p in products)
    # ADR-0044: the file's paisa survive — Sooper Ticky Pack costs Rs 4.30, not Rs 4
    assert sum(1 for p in products if p.cost_price_paisa and p.cost_price_paisa % 100) > 2000


# --- counting stock on the worklist (ADR-0047) ---------------------------------------------

def test_counting_on_the_worklist_records_a_count_and_makes_it_sellable(client, admin):
    from sukoon.models import StockMovement

    oil = _ready(client)["Sufi Oil 1L"]
    page = client.get("/stock/import/1/products").get_data(as_text=True)
    assert 'name="stock"' in page and "can't sell yet" in page
    _save(client, oil, stock="12", barcode="8964000148013")
    db.session.expire_all()
    oil = db.session.get(Product, oil.id)
    assert oil.stock_quantity_milli == 12_000
    move = db.session.scalars(db.select(StockMovement).where(
        StockMovement.product_id == oil.id)).one()
    assert (move.movement_type, move.reason) == ("correction", "Counted on the import worklist")
    _save(client, oil, stock="12")  # unchanged: no second movement
    assert db.session.query(StockMovement).filter_by(product_id=oil.id).count() == 1


def test_a_negative_or_fractional_count_is_refused(client, admin):
    oil = _ready(client)["Sufi Oil 1L"]
    for bad in ("-1", "1.5"):
        page = _save(client, oil, stock=bad).get_data(as_text=True)
        assert "be negative" in page or "whole units" in page
    db.session.expire_all()
    assert db.session.get(Product, oil.id).stock_quantity_milli == 0
