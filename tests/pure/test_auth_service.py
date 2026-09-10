"""Pure unit tests for auth_service — no database, no app context (ADR-0003)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from sukoon.services import auth_service

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_password_hash_roundtrips():
    h = auth_service.hash_password("correct horse battery staple")
    assert auth_service.verify_password(h, "correct horse battery staple")
    assert not auth_service.verify_password(h, "wrong")


def test_hash_is_not_the_plaintext():
    assert auth_service.hash_password("hunter2") != "hunter2"


@pytest.mark.parametrize(
    "attempts,expected_locked",
    [(1, False), (4, False), (5, True), (9, True)],
)
def test_compute_lockout_threshold(attempts, expected_locked):
    result = auth_service.compute_lockout(
        attempts, NOW, max_attempts=5, lockout_minutes=15
    )
    assert (result is not None) is expected_locked
    if result is not None:
        assert result == NOW + timedelta(minutes=15)


def test_is_locked_reads_future_and_past():
    future = SimpleNamespace(locked_until=NOW + timedelta(minutes=1))
    past = SimpleNamespace(locked_until=NOW - timedelta(minutes=1))
    none = SimpleNamespace(locked_until=None)
    assert auth_service.is_locked(future, NOW) is True
    assert auth_service.is_locked(past, NOW) is False
    assert auth_service.is_locked(none, NOW) is False


def test_is_locked_treats_naive_db_value_as_utc():
    naive = SimpleNamespace(locked_until=(NOW + timedelta(minutes=5)).replace(tzinfo=None))
    assert auth_service.is_locked(naive, NOW) is True


def test_resolve_user_by_login_rejects_blank_without_touching_the_db():
    assert auth_service.resolve_user_by_login("") is None
    assert auth_service.resolve_user_by_login("   ") is None


def test_verify_step_up_is_just_a_password_check():
    h = auth_service.hash_password("owner-pw")
    user = SimpleNamespace(password_hash=h)
    assert auth_service.verify_step_up(user, "owner-pw") is True
    assert auth_service.verify_step_up(user, "nope") is False
