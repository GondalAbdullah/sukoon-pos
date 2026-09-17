"""First run on a new shop PC (ADR-0038 §6): the one-time setup screen that creates the
first Admin — and every way it must refuse to."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from sukoon.app import create_app
from sukoon.extensions import db as _db
from sukoon.models import User
from sukoon.models.system import Setting
from sukoon.services import auth_service, settings_service, setup_service
from sukoon.services.auth_service import hash_password

GOOD = {"shop_name": "Al-Rehman General Store", "owner_name": "Haji Rehman",
        "password": "rehman-shop-2026", "confirm": "rehman-shop-2026"}


def _users():
    return _db.session.scalars(_db.select(User)).all()


# --- the redirect -----------------------------------------------------------------------

def test_every_page_leads_to_setup_while_there_are_no_accounts(client):
    for path in ("/", "/till/", "/khata/", "/login"):
        response = client.get(path)
        assert response.status_code == 302 and response.headers["Location"].endswith("/setup")


def test_the_stylesheet_is_still_served_so_the_setup_page_can_render(client):
    assert client.get("/static/css/tailwind.css").status_code == 200


def test_setup_is_gone_for_good_once_anyone_has_an_account(client, seeded):
    response = client.get("/setup")
    assert response.status_code == 302 and response.headers["Location"].endswith("/login")
    assert client.get("/login").status_code == 200


def test_a_database_with_only_a_cashier_never_offers_setup(client, db):
    """'No users', not 'no Admin': otherwise anyone on the network could mint an owner."""
    db.session.add(User(name="Till One", initials="T1", role="cashier",
                        password_hash=hash_password("cashier-pass")))
    db.session.commit()
    assert client.get("/setup").status_code == 302
    client.post("/setup", data=GOOD)
    assert [u.role for u in _users()] == ["cashier"]


# --- completing it ----------------------------------------------------------------------

def test_setup_creates_the_owner_names_the_shop_and_signs_them_in(client, db):
    response = client.get("/setup")
    assert response.status_code == 200 and b"Set up Sukoon" in response.data

    response = client.post("/setup", data=GOOD)
    assert response.status_code == 302 and response.headers["Location"].endswith("/")

    [owner] = _users()
    assert (owner.name, owner.initials, owner.role, owner.is_active) == \
        ("Haji Rehman", "HR", "admin", True)
    assert owner.password_hash != GOOD["password"]
    assert auth_service.verify_password(owner.password_hash, GOOD["password"])
    assert settings_service.get("shop.name") == "Al-Rehman General Store"
    assert db.session.get(Setting, setup_service.SETUP_MARKER) is not None
    with client.session_transaction() as session:
        assert session.get("_user_id") == str(owner.id)  # signed straight in


def test_the_first_owner_can_open_every_admin_screen_on_a_database_never_seeded(client, db):
    """Found in the browser, not by a test: on a database with no permission rows, the first
    owner was an 'admin' who couldn't see Khata, Insights or Messages. This fixture's
    database is exactly that — created, never seeded."""
    from sukoon.models import Permission

    assert db.session.scalars(db.select(Permission)).all() == []
    client.post("/setup", data=GOOD)
    for path in ("/till/", "/stock/", "/khata/", "/insights", "/reports", "/messages/",
                 "/refunds/pending"):  # approving refunds is Admin-only (sale.refund)
        assert client.get(path).status_code == 200, path


def test_the_owner_can_sign_in_with_the_password_they_chose(client, login):
    client.post("/setup", data=GOOD)
    client.post("/logout")
    response = login("Haji Rehman", GOOD["password"])
    assert response.status_code == 302 and "/login" not in response.headers["Location"]


def test_the_sign_in_screen_shows_the_shop_name_that_was_typed(client):
    client.post("/setup", data={**GOOD, "shop_name": "Noor Kiryana"})
    client.post("/logout")
    assert b"Noor Kiryana" in client.get("/login").data


@pytest.mark.parametrize("change,message", [
    ({"password": "short", "confirm": "short"}, b"at least 8 characters"),
    ({"confirm": "rehman-shop-2027"}, b"don&#39;t match"),
    ({"shop_name": "   "}, b"shop&#39;s name"),
    ({"owner_name": ""}, b"owner&#39;s name"),
    ({"owner_name": "x" * 121}, b"at most 120 characters"),
])
def test_mistakes_are_explained_and_create_nothing(client, change, message):
    response = client.post("/setup", data={**GOOD, **change})
    assert response.status_code == 400 and message in response.data
    assert _users() == [] and settings_service.get("shop.name") is None


def test_a_rejected_form_keeps_the_names_but_never_echoes_the_password(client):
    response = client.post("/setup", data={**GOOD, "confirm": "something-else"})
    assert b"Haji Rehman" in response.data and b"Al-Rehman General Store" in response.data
    assert GOOD["password"].encode() not in response.data


# --- where it may come from ---------------------------------------------------------------

def test_another_till_on_the_network_is_sent_to_the_shop_pc(client):
    lan = {"REMOTE_ADDR": "192.168.1.23"}
    response = client.get("/setup", environ_base=lan)
    assert response.status_code == 403 and b"on the shop PC" in response.data
    assert client.post("/setup", data=GOOD, environ_base=lan).status_code == 403
    assert _users() == []


def test_a_hostile_domain_resolved_to_this_pc_is_refused(client):
    """DNS rebinding: the connection is local, but the Host header names another site."""
    response = client.post("/setup", data=GOOD, headers={"Host": "evil.example:5000"})
    assert response.status_code == 403 and _users() == []


def test_a_form_posted_from_another_website_is_refused(client):
    response = client.post("/setup", data=GOOD, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403 and _users() == []


def test_a_same_origin_post_from_the_desktop_window_is_accepted(client):
    response = client.post("/setup", data=GOOD, headers={"Origin": "http://localhost"})
    assert response.status_code == 302 and len(_users()) == 1


# --- exactly once ---------------------------------------------------------------------------

def test_a_second_submission_after_success_creates_no_second_owner(client):
    client.post("/setup", data=GOOD)
    client.post("/logout")
    client.post("/setup", data={**GOOD, "owner_name": "Someone Else"})
    assert [u.name for u in _users()] == ["Haji Rehman"]


@pytest.fixture
def file_app(tmp_path):
    app = create_app("development", config_overrides={
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'setup.db'}",
        "SECRET_KEY": "concurrency-test-only", "TESTING": True})
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


def test_two_people_submitting_at_the_same_instant_make_exactly_one_owner(file_app):
    """Real on-disk SQLite so the two transactions genuinely contend."""
    start = threading.Barrier(2)

    def attempt(name):
        with file_app.app_context():
            start.wait()
            try:
                setup_service.complete_setup(shop_name="Shop", owner_name=name,
                                             password="long-enough-1", confirm="long-enough-1",
                                             min_length=8)
                return "created"
            except setup_service.SetupAlreadyDone:
                return "refused"
            finally:
                _db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, ["First Owner", "Second Owner"]))

    assert outcomes == ["created", "refused"]
    with file_app.app_context():
        assert len(_db.session.scalars(_db.select(User)).all()) == 1


# --- the small rules ------------------------------------------------------------------------

@pytest.mark.parametrize("name,initials", [
    ("Haji Rehman", "HR"), ("rehman", "RE"), ("  Noor  Bibi  Khan ", "NB"), ("—", "AD"),
])
def test_initials_for_the_sign_in_avatar(name, initials):
    assert setup_service.initials_for(name) == initials


def test_the_password_rule_counts_what_was_typed_including_spaces():
    auth_service.check_new_password("12345678", "12345678", min_length=8)  # exactly enough
    auth_service.check_new_password("  pad  ", "  pad  ", min_length=7)  # spaces are characters
    with pytest.raises(auth_service.WeakPasswordError, match="at least 8"):
        auth_service.check_new_password("1234567", "1234567", min_length=8)
    with pytest.raises(auth_service.WeakPasswordError, match="match"):
        auth_service.check_new_password("12345678", "12345679", min_length=8)
