"""The seed script's reference data (Development Specification Phase 1 step 5)."""
from __future__ import annotations

from sukoon.extensions import db
from sukoon.models import Category, Permission, Product, RolePermission, User
from sukoon.seed import seed_all, seed_permissions
from sukoon.services.auth_service import (
    permission_codes_for_role,
    role_has_permission,
)
from sukoon.services.permissions import PERMISSIONS, ROLE_PERMISSIONS


def test_seed_permissions_creates_the_catalogue(app):
    seed_permissions()
    assert db.session.query(Permission).count() == len(PERMISSIONS)


def test_seed_permissions_is_idempotent(app):
    seed_permissions()
    seed_permissions()
    assert db.session.query(Permission).count() == len(PERMISSIONS)
    assert db.session.query(RolePermission).count() == sum(
        len(codes) for codes in ROLE_PERMISSIONS.values()
    )


def test_admin_holds_every_code_cashier_a_subset(app):
    seed_permissions()
    assert permission_codes_for_role("admin") == set(PERMISSIONS)
    cashier = permission_codes_for_role("cashier")
    assert "product.edit_price" not in cashier
    assert "sale.refund" not in cashier
    assert "sale.ring" in cashier


def test_role_has_permission_helper(app):
    seed_permissions()
    assert role_has_permission("admin", "sale.refund") is True
    assert role_has_permission("cashier", "sale.refund") is False
    assert role_has_permission("cashier", "no.such.code") is False


def test_seed_all_creates_dev_users_and_a_sample_catalogue(app):
    seed_all(with_sample_data=True)
    assert db.session.query(User).count() == 2
    assert {u.role for u in db.session.query(User).all()} == {"admin", "cashier"}
    assert db.session.query(Category).count() == 2
    assert db.session.query(Product).count() == 3
    # a provisional product is flagged, not silently zero-costed (ADR-0011)
    provisional = db.session.query(Product).filter_by(is_provisional=True).one()
    assert provisional.cost_price_paisa is None


def test_seed_all_is_idempotent(app):
    seed_all(with_sample_data=True)
    seed_all(with_sample_data=True)
    assert db.session.query(User).count() == 2
    assert db.session.query(Product).count() == 3


def test_a_changed_description_is_refreshed_without_touching_the_row(app):
    seed_permissions()
    perm = db.session.scalars(db.select(Permission).where(Permission.code == "sale.ring")).one()
    original_id = perm.id
    perm.description = "stale wording from an older release"
    db.session.commit()
    seed_permissions()
    db.session.expire_all()
    perm = db.session.scalars(db.select(Permission).where(Permission.code == "sale.ring")).one()
    assert perm.id == original_id and perm.description == PERMISSIONS["sale.ring"]


def test_two_processes_seeding_at_the_same_instant_both_succeed(tmp_path):
    """Setup (and, from Phase 7 part 2, every start-up) seeds permissions. The old
    read-then-insert raised UNIQUE constraint failed when two ran at once."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sukoon.app import create_app

    file_app = create_app("development", config_overrides={
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'seed.db'}",
        "SECRET_KEY": "concurrency-test-only", "TESTING": True})
    with file_app.app_context():
        db.create_all()
    start = threading.Barrier(4)

    def seed():
        with file_app.app_context():
            start.wait()
            try:
                seed_permissions()
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(seed) for _ in range(4)]:
            future.result()  # re-raises an IntegrityError from any thread

    with file_app.app_context():
        assert db.session.query(Permission).count() == len(PERMISSIONS)
        assert db.session.query(RolePermission).count() == sum(
            len(codes) for codes in ROLE_PERMISSIONS.values())
        db.drop_all()
