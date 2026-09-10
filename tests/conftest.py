"""Shared pytest fixtures. Per Development Specification Section 10: integration
tests use pytest-flask against a real app instance with a real (in-memory) SQLite
database — no mocking framework."""
from __future__ import annotations

import pytest

from sukoon.app import create_app
from sukoon.extensions import db as _db
from sukoon.models.user import User
from sukoon.seed import seed_permissions
from sukoon.services.auth_service import hash_password

ADMIN_PASSWORD = "admin-pass-test"
CASHIER_PASSWORD = "cashier-pass-test"


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded(db):
    """The permission catalogue plus one Admin and one Cashier with known
    passwords."""
    seed_permissions()
    admin = User(
        name="Owner",
        initials="OW",
        role="admin",
        password_hash=hash_password(ADMIN_PASSWORD),
    )
    cashier = User(
        name="Till One",
        initials="T1",
        role="cashier",
        password_hash=hash_password(CASHIER_PASSWORD),
    )
    db.session.add_all([admin, cashier])
    db.session.commit()
    return {"admin": admin, "cashier": cashier}


@pytest.fixture
def login(client):
    def _login(identifier: str, password: str):
        return client.post(
            "/login",
            data={"identifier": identifier, "password": password},
            follow_redirects=False,
        )

    return _login
