"""Staff accounts: the Admin adds the shop's cashiers (ADR-0008, ADR-0017).

Until now the only account Sukoon could create was the owner's, on the setup screen — so a shop
with cashiers had no way to let them sign in at all. Found by the developer the day before
go-live, testing as Admin.

Three rules keep this from becoming a way to lose the shop:

* **Accounts are deactivated, never deleted.** A user is on every sale, stock movement, refund and
  Khata entry they touched (ADR-0016); deleting one would orphan that history.
* **The last active Admin cannot be deactivated or demoted.** Otherwise a shop can lock itself out
  of its own prices, refunds and reports, with no way back in.
* **Names and initials must be distinct**, because sign-in accepts either (ADR-0017).

No Flask import here (ADR-0003 §1).
"""
from __future__ import annotations

from sqlalchemy import func, select

from sukoon.extensions import db
from sukoon.models.user import ROLE_ADMIN, ROLES, User
from sukoon.services import auth_service

NAME_MAX = 120
INITIALS_MAX = 8


class StaffError(ValueError):
    """Something the Admin typed needs fixing. The message says what."""


def list_staff() -> list[User]:
    return list(db.session.scalars(select(User).order_by(User.is_active.desc(), User.name)))


def active_admins(exclude_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.role == ROLE_ADMIN, User.is_active.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.session.scalar(stmt) or 0


def _taken(value: str, column, exclude_id: int | None) -> bool:
    stmt = select(func.count()).select_from(User).where(func.lower(column) == value.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return (db.session.scalar(stmt) or 0) > 0


def initials_for(name: str, *, exclude_id: int | None = None) -> str:
    """'Nadia Bibi' → 'NB'. Distinct: sign-in accepts initials, so a second NB becomes NB2."""
    words = [w for w in name.split() if w[:1].isalnum()]
    base = (words[0][:2] if len(words) == 1 else words[0][0] + words[1][0]).upper() if words \
        else "ST"
    candidate, suffix = base, 1
    while _taken(candidate, User.initials, exclude_id):
        suffix += 1
        candidate = f"{base}{suffix}"[:INITIALS_MAX]
    return candidate


def add_staff(*, name: str, role: str, password: str, confirm: str, min_length: int) -> User:
    name = (name or "").strip()
    if not name:
        raise StaffError("Type the person's name — it's what they'll choose when signing in.")
    if len(name) > NAME_MAX:
        raise StaffError(f"Names can be at most {NAME_MAX} characters.")
    if role not in ROLES:
        raise StaffError("Choose whether this person is a cashier or an admin.")
    if _taken(name, User.name, None):
        raise StaffError(f"Someone called {name} already has an account. Use a fuller name.")
    try:
        auth_service.check_new_password(password, confirm, min_length=min_length)
    except auth_service.WeakPasswordError as exc:
        raise StaffError(str(exc)) from exc

    user = User(name=name, initials=initials_for(name), role=role,
                password_hash=auth_service.hash_password(password), is_active=True)
    db.session.add(user)
    db.session.commit()
    return user


def set_password(user: User, *, password: str, confirm: str, min_length: int) -> None:
    try:
        auth_service.check_new_password(password, confirm, min_length=min_length)
    except auth_service.WeakPasswordError as exc:
        raise StaffError(str(exc)) from exc
    user.password_hash = auth_service.hash_password(password)
    user.failed_login_attempts = 0     # a new password also ends a lockout (ADR-0017)
    user.locked_until = None
    db.session.commit()


def set_active(user: User, *, active: bool) -> None:
    if not active and user.role == ROLE_ADMIN and active_admins(exclude_id=user.id) == 0:
        raise StaffError(
            f"{user.name} is the only admin left. Make someone else an admin first, or the shop "
            f"would have nobody who can change prices, approve refunds or see Insights.")
    user.is_active = active
    if active:
        user.failed_login_attempts = 0
        user.locked_until = None
    db.session.commit()


def set_role(user: User, *, role: str) -> None:
    if role not in ROLES:
        raise StaffError("Choose whether this person is a cashier or an admin.")
    if role != ROLE_ADMIN and user.role == ROLE_ADMIN and active_admins(exclude_id=user.id) == 0:
        raise StaffError(f"{user.name} is the only admin left; make someone else an admin first.")
    user.role = role
    db.session.commit()
