"""Authentication and authorisation logic (ADR-0008).

No Flask import lives in this module (ADR-0003 §1) — it takes plain values and a
``now`` timestamp, so every branch here is unit-testable with no app context.
Werkzeug's password hashing is used directly (ADR-0001); Werkzeug is not Flask.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from sukoon.extensions import db
from sukoon.models.user import Permission, RolePermission, User


class AuthError(Exception):
    """Base class for every authentication failure (ADR-0003 §5)."""


class InvalidCredentialsError(AuthError):
    """The name/password pair did not match an active account."""


class AccountLockedError(AuthError):
    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        super().__init__("Account is temporarily locked.")


class AccountInactiveError(AuthError):
    """The account exists but has been deactivated."""


def _aware(value: datetime | None) -> datetime | None:
    """Treat a naive datetime (SQLite round-trips as naive) as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def hash_password(plain: str) -> str:
    return generate_password_hash(plain)


def verify_password(password_hash: str, plain: str) -> bool:
    return check_password_hash(password_hash, plain)


def is_locked(user: User, now: datetime) -> bool:
    locked_until = _aware(user.locked_until)
    return locked_until is not None and locked_until > now


def compute_lockout(
    attempts: int, now: datetime, *, max_attempts: int, lockout_minutes: int
) -> datetime | None:
    """Pure: given a post-increment attempt count, the lockout expiry (or None if
    the account is not yet locked)."""
    if attempts >= max_attempts:
        return now + timedelta(minutes=lockout_minutes)
    return None


def register_failed_login(
    user: User, now: datetime, *, max_attempts: int, lockout_minutes: int
) -> None:
    """Increment the failure counter and, at the threshold, set a lockout window.
    The counter is not reset here — it clears only on a successful login."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    user.locked_until = compute_lockout(
        user.failed_login_attempts,
        now,
        max_attempts=max_attempts,
        lockout_minutes=lockout_minutes,
    )
    db.session.add(user)


def register_successful_login(user: User, now: datetime) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.session.add(user)


def resolve_user_by_login(identifier: str) -> User | None:
    """Look a user up by name (case-insensitive) or by initials."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    return db.session.scalars(
        db.select(User).where(
            db.func.lower(User.name) == ident.lower()
        )
    ).first() or db.session.scalars(
        db.select(User).where(db.func.lower(User.initials) == ident.lower())
    ).first()


def authenticate(
    identifier: str,
    password: str,
    now: datetime,
    *,
    max_attempts: int,
    lockout_minutes: int,
) -> User:
    """Return the authenticated user, or raise a precise AuthError.

    A missing user and a wrong password raise the *same* error, so the form
    cannot be used to enumerate valid accounts.
    """
    user = resolve_user_by_login(identifier)
    if user is None:
        raise InvalidCredentialsError("Incorrect name or password.")

    if is_locked(user, now):
        raise AccountLockedError(_aware(user.locked_until))

    if not user.is_active:
        raise AccountInactiveError("This account has been deactivated.")

    if not verify_password(user.password_hash, password):
        register_failed_login(
            user, now, max_attempts=max_attempts, lockout_minutes=lockout_minutes
        )
        raise InvalidCredentialsError("Incorrect name or password.")

    register_successful_login(user, now)
    return user


def verify_step_up(user: User, password: str) -> bool:
    """A fresh password re-entry for a single destructive action (ADR-0008 §5).
    Deliberately does not touch the lockout counters — step-up is not a login."""
    return verify_password(user.password_hash, password)


def permission_codes_for_role(role: str) -> set[str]:
    rows = db.session.scalars(
        db.select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role == role)
    ).all()
    return set(rows)


def role_has_permission(role: str, code: str) -> bool:
    """Authorisation is always a permission-code check, never ``role == 'admin'``
    inline at a call site (ADR-0008 §3)."""
    return db.session.scalar(
        db.select(db.func.count())
        .select_from(RolePermission)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role == role, Permission.code == code)
    ) > 0
