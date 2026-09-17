"""Staff accounts (ADR-0008, ADR-0017).

Found the day before go-live: Sukoon could create exactly one account — the owner's, on the setup
screen — so a shop with cashiers had no way to let them sign in at all.
"""
from __future__ import annotations

import pytest

from sukoon.extensions import db
from sukoon.models.user import ROLE_ADMIN, ROLE_CASHIER, User
from sukoon.services import auth_service, staff_service
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

NEW = {"name": "Nadia Bibi", "role": "cashier", "password": "nadia-till-2026",
       "confirm": "nadia-till-2026", "step_up_password": ADMIN_PASSWORD}


def _named(name):
    return db.session.scalars(db.select(User).where(User.name == name)).first()


# --- who may use it ------------------------------------------------------------------------

def test_a_cashier_cannot_reach_staff_at_all(client, seeded, login):
    login("T1", CASHIER_PASSWORD)
    assert client.get("/staff/").status_code == 403
    assert client.post("/staff/", data=NEW).status_code == 403
    assert _named("Nadia Bibi") is None


def test_the_admin_sees_everyone(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    page = client.get("/staff/")
    assert page.status_code == 200
    assert b"Owner" in page.data and b"Till One" in page.data


# --- adding ---------------------------------------------------------------------------------

def test_adding_a_cashier_lets_them_sign_in(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    assert client.post("/staff/", data=NEW).status_code == 302
    nadia = _named("Nadia Bibi")
    assert nadia is not None and nadia.role == ROLE_CASHIER and nadia.is_active
    assert nadia.password_hash != NEW["password"]

    client.post("/logout")
    response = login("Nadia Bibi", "nadia-till-2026")
    assert response.status_code == 302 and "/login" not in response.headers["Location"]
    assert client.get("/till/").status_code == 200      # a cashier's screen
    assert client.get("/insights").status_code == 403   # not an admin's


def test_adding_someone_needs_the_admins_own_password(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    for bad in ({**NEW, "step_up_password": "not-the-password"}, {k: v for k, v in NEW.items()
                                                                 if k != "step_up_password"}):
        assert client.post("/staff/", data=bad).status_code == 403
    assert _named("Nadia Bibi") is None


@pytest.mark.parametrize("change,message", [
    ({"name": "  "}, b"person&#39;s name"),
    ({"name": "Owner"}, b"already has an account"),
    ({"password": "short", "confirm": "short"}, b"at least 8 characters"),
    ({"confirm": "something-else"}, b"don&#39;t match"),
    ({"role": "wizard"}, b"cashier or an admin"),
])
def test_mistakes_are_explained_and_nobody_is_created(client, seeded, login, change, message):
    login("Owner", ADMIN_PASSWORD)
    before = db.session.query(User).count()
    response = client.post("/staff/", data={**NEW, **change})
    assert response.status_code == 400 and message in response.data
    assert db.session.query(User).count() == before


def test_initials_stay_distinct_because_sign_in_accepts_them(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    client.post("/staff/", data=NEW)                                  # Nadia Bibi -> NB
    client.post("/staff/", data={**NEW, "name": "Nasir Baig"})        # would also be NB
    assert {u.initials for u in db.session.query(User).all()} == {"OW", "T1", "NB", "NB2"}


# --- changing -------------------------------------------------------------------------------

def test_an_admin_can_reset_a_forgotten_password_and_free_a_locked_account(client, seeded, login):
    cashier = seeded["cashier"]
    cashier.failed_login_attempts = 5
    db.session.commit()
    login("Owner", ADMIN_PASSWORD)
    response = client.post(f"/staff/{cashier.id}/password",
                           data={"password": "new-till-password", "confirm": "new-till-password",
                                 "step_up_password": ADMIN_PASSWORD})
    assert response.status_code == 302
    db.session.refresh(cashier)
    assert auth_service.verify_password(cashier.password_hash, "new-till-password")
    assert cashier.failed_login_attempts == 0 and cashier.locked_until is None


def test_switching_someone_off_stops_them_signing_in_but_keeps_their_history(client, seeded, login):
    cashier = seeded["cashier"]
    login("Owner", ADMIN_PASSWORD)
    assert client.post(f"/staff/{cashier.id}/active",
                       data={"active": "0", "step_up_password": ADMIN_PASSWORD}).status_code == 302
    db.session.refresh(cashier)
    assert cashier.is_active is False and db.session.get(User, cashier.id) is not None

    client.post("/logout")
    assert login("T1", CASHIER_PASSWORD).status_code == 401


def test_the_last_admin_cannot_switch_themselves_off_or_become_a_cashier(client, seeded, login):
    owner = seeded["admin"]
    login("Owner", ADMIN_PASSWORD)

    off = client.post(f"/staff/{owner.id}/active",
                      data={"active": "0", "step_up_password": ADMIN_PASSWORD})
    assert off.status_code == 400 and b"only admin left" in off.data

    demote = client.post(f"/staff/{owner.id}/role",
                         data={"role": "cashier", "step_up_password": ADMIN_PASSWORD})
    assert demote.status_code == 400 and b"only admin left" in demote.data

    db.session.refresh(owner)
    assert owner.is_active and owner.role == ROLE_ADMIN   # the shop can still be administered


def test_a_second_admin_makes_the_first_one_removable(client, seeded, login):
    login("Owner", ADMIN_PASSWORD)
    client.post("/staff/", data={**NEW, "name": "Second Owner", "role": "admin"})
    owner = seeded["admin"]
    assert client.post(f"/staff/{owner.id}/active",
                       data={"active": "0", "step_up_password": ADMIN_PASSWORD}).status_code == 302
    db.session.refresh(owner)
    assert owner.is_active is False


def test_promoting_a_cashier_gives_them_the_admin_screens(client, seeded, login):
    cashier = seeded["cashier"]
    login("Owner", ADMIN_PASSWORD)
    promote = client.post(f"/staff/{cashier.id}/role",
                          data={"role": "admin", "step_up_password": ADMIN_PASSWORD})
    assert promote.status_code == 302
    client.post("/logout")
    login("T1", CASHIER_PASSWORD)
    assert client.get("/insights").status_code == 200


def test_the_service_refuses_to_leave_the_shop_without_an_admin(app, seeded):
    with pytest.raises(staff_service.StaffError, match="only admin"):
        staff_service.set_active(seeded["admin"], active=False)
    assert staff_service.active_admins() == 1
