"""Auth flow and authorization tests (Development Specification Phase 1,
ADR-0008): login success/failure, logout, lockout, and a Cashier hitting an
Admin-only route getting a real server-side 403."""
from __future__ import annotations

from datetime import UTC, datetime

from sukoon.extensions import db
from sukoon.models import User
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


def test_successful_login_redirects_and_sets_session(client, seeded, login):
    resp = login("Owner", ADMIN_PASSWORD)
    assert resp.status_code == 302
    # last_login_at recorded
    admin = db.session.get(User, seeded["admin"].id)
    assert admin.last_login_at is not None
    assert admin.failed_login_attempts == 0


def test_login_by_initials_also_works(client, seeded, login):
    assert login("T1", CASHIER_PASSWORD).status_code == 302


def test_failed_login_increments_attempts_and_401s(client, seeded, login):
    resp = login("Owner", "nope")
    assert resp.status_code == 401
    admin = db.session.get(User, seeded["admin"].id)
    assert admin.failed_login_attempts == 1


def test_unknown_user_and_wrong_password_are_indistinguishable(client, seeded, login):
    a = login("Owner", "nope")
    b = login("ghost", "nope")
    assert a.status_code == b.status_code == 401


def test_lockout_after_five_failures_then_rejects_correct_password(client, seeded, login):
    for _ in range(5):
        login("Owner", "wrong")
    admin = db.session.get(User, seeded["admin"].id)
    assert admin.locked_until is not None
    # Even the correct password is refused while locked.
    resp = login("Owner", ADMIN_PASSWORD)
    assert resp.status_code == 429


def test_lockout_expires(client, seeded, login, app):
    admin = db.session.get(User, seeded["admin"].id)
    admin.locked_until = datetime.now(UTC).replace(year=2000)
    admin.failed_login_attempts = 5
    db.session.commit()
    # A past lock does not block.
    assert login("Owner", ADMIN_PASSWORD).status_code == 302


def test_logout_clears_session(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    assert client.post("/logout").status_code == 302
    # protected route now redirects to login
    resp = client.get("/admin/price-check")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_cashier_hitting_admin_route_gets_403_not_a_redirect(client, seeded, login):
    login("T1", CASHIER_PASSWORD)
    resp = client.get("/admin/price-check")
    assert resp.status_code == 403


def test_admin_reaches_admin_route(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    resp = client.get("/admin/price-check")
    assert resp.status_code == 200
    assert b"admin area" in resp.data


def test_anonymous_is_redirected_to_login(client, seeded):
    resp = client.get("/admin/price-check")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_deactivated_account_cannot_log_in(client, seeded, login):
    admin = db.session.get(User, seeded["admin"].id)
    admin.is_active = False
    db.session.commit()
    resp = login("Owner", ADMIN_PASSWORD)
    assert resp.status_code == 401


def test_permission_check_is_by_code_not_role_name(client, seeded, login):
    """ADR-0008 §3: even role 'admin' is denied when the permission row is absent."""
    from sukoon.models import Permission, RolePermission

    perm = db.session.scalars(
        db.select(Permission).where(Permission.code == "product.edit_price")
    ).first()
    db.session.query(RolePermission).filter_by(
        role="admin", permission_id=perm.id
    ).delete()
    db.session.commit()

    login("Owner", ADMIN_PASSWORD)
    assert client.get("/admin/price-check").status_code == 403
