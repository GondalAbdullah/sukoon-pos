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
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from sukoon.extensions import db
from sukoon.models import (
    Category,
    InvoiceCounter,
    Permission,
    Product,
    RolePermission,
    User,
)
from sukoon.models.user import ROLE_ADMIN, ROLE_CASHIER
from sukoon.services.auth_service import hash_password
from sukoon.services.permissions import PERMISSIONS, ROLE_PERMISSIONS

log = logging.getLogger(__name__)

_DEV_PLACEHOLDER = "sukoon-dev-only-change-me"


def seed_permissions() -> None:
    """Idempotent, and safe when two processes run it at once.

    It used to read the existing rows and then insert the missing ones. That was fine while
    only ``flask seed`` called it; Phase 7's setup screen calls it too, and two people
    submitting setup at the same instant both saw no permissions and both inserted —
    ``UNIQUE constraint failed: permission.code``, found by the setup concurrency test. The
    same read-then-insert race Phase 5 found in ``settings_service.set``, fixed the same way:
    each row is one insert that lets the unique constraint decide.
    """
    for code, description in PERMISSIONS.items():
        db.session.execute(
            sqlite_insert(Permission)
            .values(code=code, description=description)
            .on_conflict_do_update(index_elements=[Permission.code],
                                   set_={"description": description})
        )
    ids = dict(db.session.execute(db.select(Permission.code, Permission.id)).all())
    for role, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            db.session.execute(
                sqlite_insert(RolePermission)
                .values(role=role, permission_id=ids[code])
                .on_conflict_do_nothing(
                    index_elements=[RolePermission.role, RolePermission.permission_id])
            )
    db.session.commit()


def seed_invoice_counter() -> None:
    """Reference data the sale flow needs (ADR-0016): the single counter row.
    Idempotent; the current calendar year seeds the first sequence."""
    if db.session.get(InvoiceCounter, 1) is None:
        db.session.add(
            InvoiceCounter(
                id=1,
                prefix="INV",
                year=datetime.now(UTC).year,
                next_sequence=1,
            )
        )
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
    seed_invoice_counter()
    if with_sample_data:
        seed_dev_users()
        seed_sample_catalog()
