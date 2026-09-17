"""Sign-in hardening found while building Phase 7's setup screen: an open redirect after
sign-in, and a session cookie whose cross-site behaviour was left to the browser."""
from __future__ import annotations

import pytest

from sukoon.routes.auth import _safe_next
from tests.conftest import ADMIN_PASSWORD


@pytest.mark.parametrize("target,expected", [
    ("/khata/", "/khata/"),
    ("/till/?terminal=1", "/till/?terminal=1"),
    ("https://evil.example/login", None),
    ("//evil.example/login", None),
    ("/\\evil.example/login", None),
    ("javascript:alert(1)", None),
    ("khata", None),
    ("", None),
    (None, None),
])
def test_only_paths_inside_sukoon_are_followed_after_sign_in(target, expected):
    assert _safe_next(target) == expected


def test_signing_in_with_a_hostile_next_lands_on_sukoon_not_elsewhere(client, seeded):
    response = client.post("/login?next=https://evil.example/login",
                           data={"identifier": "Owner", "password": ADMIN_PASSWORD})
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


def test_signing_in_with_a_real_next_still_goes_there(client, seeded):
    response = client.post("/login?next=/khata/",
                           data={"identifier": "Owner", "password": ADMIN_PASSWORD})
    assert response.headers["Location"].endswith("/khata/")


def test_the_session_cookie_is_lax_and_hidden_from_scripts(client, seeded):
    response = client.post("/login", data={"identifier": "Owner", "password": ADMIN_PASSWORD})
    cookie = response.headers["Set-Cookie"]
    assert "SameSite=Lax" in cookie and "HttpOnly" in cookie
