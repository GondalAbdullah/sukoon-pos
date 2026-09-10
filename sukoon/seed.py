"""Seed data for local development and tests.

Two layers:

* ``seed_permissions`` — the permission catalogue and role→permission rows from
  ADR-0008 / ``services/permissions.py``. This is *reference data the app needs to
  function*, not sample data; every environment runs it.
* ``seed_dev_users`` / ``seed_sample_catalog`` — throwaway data for poking at the
  app by hand. Never runs in production.

Dev-user passwords come from the environment (``SEED_ADMIN_PASSWORD``,
``SEED_CASHIER_PASSWORD``); if unset, a loud placeholder is used and a warning is
logged. No real credential is ever hardcoded (Operating Rule 6).
"""
from __future__ import annotations

import logging
import os

from sukoon.extensions import db
from sukoon.models import Category, Permission, Product, RolePermission, User
from sukoon.models.user import ROLE_ADMIN, ROLE_CASHIER
from sukoon.services.auth_service import hash_password
from sukoon.services.permissions import PERMISSIONS, ROLE_PERMISSIONS

log = logging.getLogger(__name__)

_DEV_PLACEHOLDER = "sukoon-dev-only-change-me"


def seed_permissions() -> None:
    """Idempotent: upserts every permission code and its role mappings."""
    by_code: dict[str, Permission] = {
        p.code: p for p in db.session.scalars(db.select(Permission)).all()
    }
    for code, description in PERMISSIONS.items():
        perm = by_code.get(code)
        if perm is None:
            perm = Permission(code=code, description=description)
            db.session.add(perm)
            db.session.flush()
            by_code[code] = perm
        else:
            perm.description = description

    existing = {
        (rp.role, rp.permission_id)
        for rp in db.session.scalars(db.select(RolePermission)).all()
    }
    for role, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            pid = by_code[code].id
            if (role, pid) not in existing:
                db.session.add(RolePermission(role=role, permission_id=pid))
    db.session.commit()


def _password_from_env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        log.warning(
            "%s not set — seeding a placeholder password. Do not use this "
            "outside local development.",
            var,
        )
        return _DEV_PLACEHOLDER
    return value


def seed_dev_users() -> None:
    if db.session.scalar(db.select(db.func.count()).select_from(User)):
        return
    db.session.add_all(
        [
            User(
                name="Abdullah",
                initials="AD",
                role=ROLE_ADMIN,
                password_hash=hash_password(_password_from_env("SEED_ADMIN_PASSWORD")),
            ),
            User(
                name="Sana",
                initials="SN",
                role=ROLE_CASHIER,
                password_hash=hash_password(
                    _password_from_env("SEED_CASHIER_PASSWORD")
                ),
            ),
        ]
    )
    db.session.commit()


def seed_sample_catalog() -> None:
    if db.session.scalar(db.select(db.func.count()).select_from(Product)):
        return
    groceries = Category(name="Groceries", display_order=1)
    household = Category(name="Household", display_order=2)
    db.session.add_all([groceries, household])
    db.session.flush()
    db.session.add_all(
        [
            Product(
                name="Atta (loose)",
                unit_label="kg",
                allows_fractional=True,
                sell_price_paisa=17_000,
                category_id=groceries.id,
            ),
            Product(
                name="Cooking Oil 1L",
                unit_label="bottle",
                sell_price_paisa=59_000,
                cost_price_paisa=52_000,
                category_id=groceries.id,
            ),
            Product(
                name="Dish Soap 500ml",
                unit_label="bottle",
                sell_price_paisa=28_000,
                category_id=household.id,
                is_provisional=True,  # no cost price yet
            ),
        ]
    )
    db.session.commit()


def seed_all(*, with_sample_data: bool = True) -> None:
    seed_permissions()
    if with_sample_data:
        seed_dev_users()
        seed_sample_catalog()
