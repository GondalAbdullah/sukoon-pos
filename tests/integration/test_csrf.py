"""CSRF protection on every form and htmx request (context.md §4: required before Sukoon is
on the shop's network). The rest of the suite runs with CSRF off; these tests turn it on."""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from itsdangerous import TimestampSigner

from sukoon.app import create_app
from sukoon.extensions import db as _db
from sukoon.models.user import User
from sukoon.seed import seed_permissions
from sukoon.services.auth_service import hash_password

TEMPLATES = Path(__file__).resolve().parents[2] / "sukoon" / "templates"
PASSWORD = "owner-pass-test"


def _form_tags(text):
    """Opening <form> tags, found by scanning: quotes and {{ }} / {% %} can hold '>' and '{',
    which fooled a regex into treating a GET form and the POST form after it as one tag."""
    for start in (m.start() for m in re.finditer(r"<form\b", text, re.I)):
        i, quote = start + 5, None
        while i < len(text):
            if quote:
                quote = None if text[i] == quote else quote
                i += 1
            elif text.startswith(("{{", "{%"), i):
                i = text.index("}}" if text.startswith("{{", i) else "%}", i) + 2
            elif text[i] in "\"'":
                quote, i = text[i], i + 1
            elif text[i] == ">":
                yield text[start:i + 1], text[i + 1:]
                break
            else:
                i += 1


def test_every_post_form_in_every_template_carries_the_token():
    """So a form added later without one fails here, not in the shop."""
    missing, checked = [], 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        for tag, rest in _form_tags(path.read_text(encoding="utf-8")):
            if not re.search(r'\bmethod\s*=\s*["\']post["\']', tag, re.I):
                continue
            checked += 1
            body = rest[: rest.lower().find("</form>")]
            if 'name="csrf_token"' not in body:
                missing.append(f"{path.relative_to(TEMPLATES)}: {' '.join(tag.split())[:80]}")
    assert checked >= 42 and missing == []


@pytest.fixture
def app():
    application = create_app("testing", config_overrides={"WTF_CSRF_ENABLED": True})
    with application.app_context():
        _db.create_all()
        seed_permissions()
        _db.session.add(User(name="Owner", initials="OW", role="admin",
                             password_hash=hash_password(PASSWORD)))
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()


def _token(page_html: bytes) -> str:
    return re.search(rb'name="csrf_token" value="([^"]+)"', page_html).group(1).decode()


def _signed_in(client):
    token = _token(client.get("/login").data)
    client.post("/login", data={"identifier": "Owner", "password": PASSWORD, "csrf_token": token})
    with client.session_transaction() as session:
        assert session.get("_user_id")
    return token


def test_a_post_without_the_token_is_refused_and_nothing_happens(app):
    client = app.test_client()
    response = client.post("/login", data={"identifier": "Owner", "password": PASSWORD})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert not session.get("_user_id")  # not signed in: the view never ran
    assert b"nothing was saved" in client.get("/login").data


def test_the_token_from_the_page_is_accepted(app):
    client = app.test_client()
    _signed_in(client)  # asserts the sign-in succeeded with the page's own token


def test_a_rejected_htmx_request_reloads_the_page_instead_of_silently_doing_nothing(app):
    client = app.test_client()
    _signed_in(client)
    response = client.post("/logout", headers={"HX-Request": "true"})
    assert response.status_code == 400 and response.headers["HX-Refresh"] == "true"
    with client.session_transaction() as session:
        assert session.get("_user_id")  # still signed in: logout never ran


def test_htmx_may_send_the_token_as_a_header(app):
    client = app.test_client()
    token = _signed_in(client)
    response = client.post("/logout", headers={"HX-Request": "true", "X-CSRFToken": token})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert not session.get("_user_id")


def test_a_rejection_never_redirects_to_another_site(app):
    client = app.test_client()
    response = client.post("/login", data={}, headers={"Referer": "https://evil.example/x"})
    assert "evil.example" not in response.headers["Location"]


def test_a_till_left_open_over_lunch_can_still_ring_a_sale(app, monkeypatch):
    """Flask-WTF's tokens expire after an hour by default. A cashier who opened the till at
    11:00 and rings the next sale at 14:00 must not be told 'nothing was saved'."""
    client = app.test_client()
    token = _token(client.get("/login").data)
    three_hours_later = int(time.time()) + 3 * 3600
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: three_hours_later)
    client.post("/login", data={"identifier": "Owner", "password": PASSWORD, "csrf_token": token})
    with client.session_transaction() as session:
        assert session.get("_user_id")
