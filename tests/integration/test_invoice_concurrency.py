"""Concurrent checkout — invoice numbering has no duplicates and no gaps under
concurrent checkouts (Development Specification Phase 3 Required Test; edge-case
matrix 'POS / Billing' and 'Inventory: concurrent stock updates').

Uses a real on-disk SQLite database in WAL mode with a thread pool, so the
threads genuinely contend for the counter row's write lock — the in-memory test
database shares one connection and could not exercise this.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from sukoon.app import create_app
from sukoon.extensions import db
from sukoon.models import Product, User
from sukoon.seed import seed_invoice_counter
from sukoon.services import inventory_service as inv
from sukoon.services import sales_service
from sukoon.services.auth_service import hash_password
from sukoon.services.sales_service import CartLine

JAN_2026 = datetime(2026, 1, 15, tzinfo=UTC)


@pytest.fixture
def file_app(tmp_path):
    app = create_app(
        "development",
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'concurrency.db'}",
            "SECRET_KEY": "concurrency-test-only",
            "TESTING": True,
        },
    )
    with app.app_context():
        db.create_all()
        seed_invoice_counter()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_concurrent_claims_have_no_duplicates_and_no_gaps(file_app):
    total = 50

    def claim_one(_: int) -> str:
        with file_app.app_context():
            number = sales_service.claim_invoice_number()
            db.session.commit()
            db.session.remove()
            return number

    with ThreadPoolExecutor(max_workers=10) as pool:
        numbers = list(pool.map(claim_one, range(total)))

    sequences = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert len(set(numbers)) == total, "a number was handed out twice"
    assert sequences == list(range(1, total + 1)), "the sequence has a gap"


def test_concurrent_sales_of_one_product_do_not_lose_a_stock_update(file_app):
    """Two terminals selling the same item at once: every deduction lands, none
    is lost (edge-case matrix 'concurrent stock updates ... without lost
    updates'). The atomic invoice-number claim serialises the sale
    transactions on the counter row, so a later sale always sees the earlier
    one's committed deduction.
    """
    sales = 30
    with file_app.app_context():
        u = User(name="T", initials="T", role="cashier", password_hash=hash_password("x"))
        db.session.add(u)
        db.session.commit()
        user_id = u.id
        p = inv.create_product(name="Egg", sell_price_paisa=2_000)
        inv.apply_stock_movement(
            product=p, movement_type="stock_in", quantity_milli=sales * 1_000,
            reason="in", user_id=user_id,
        )
        product_id = p.id

    def ring(_: int) -> None:
        with file_app.app_context():
            product = db.session.get(Product, product_id)
            sales_service.record_sale(
                lines=[CartLine(product=product, quantity_milli=1_000,
                                unit_price_paisa=2_000, quantity_source="stepper")],
                payment_method="cash", user_id=user_id, now=JAN_2026,
            )
            db.session.remove()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(ring, range(sales)))

    with file_app.app_context():
        assert db.session.get(Product, product_id).stock_quantity_milli == 0
