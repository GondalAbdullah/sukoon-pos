"""First run on a new shop PC (ADR-0038 §6).

An installed copy has no accounts, and the shop owner has no terminal to run ``flask seed``
with. So the first person to open Sukoon on the shop PC sees a one-time setup screen: the
shop's name, and the owner's name and password, which becomes the first Admin.

Two rules make that safe rather than merely convenient:

* **Once, ever.** Setup is available only while the database has *no users at all* — not
  "no Admin". A database holding only a cashier must never offer anyone on the network a way
  to mint an Admin. Completing it claims a marker row atomically, so two people submitting
  the form at the same instant can't create two owners.
* **From the shop PC only** — enforced in the route, where the request's origin is known.

No Flask import here (ADR-0003 §1).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from sukoon.extensions import db
from sukoon.models.base import utcnow
from sukoon.models.system import Setting
from sukoon.models.user import ROLE_ADMIN, User
from sukoon.seed import seed_permissions
from sukoon.services import auth_service, settings_service

SETUP_MARKER = "setup.completed_at"
SHOP_NAME_KEY = "shop.name"
NAME_MAX = 120


class SetupError(ValueError):
    """Something the person typed needs fixing. The message says what."""


class SetupAlreadyDone(RuntimeError):
    """Setup has already happened — possibly by someone else a moment ago."""


def needs_setup() -> bool:
    return db.session.scalar(select(func.count()).select_from(User)) == 0


def initials_for(name: str) -> str:
    """'Haji Usman' → 'HU'; 'Rehman' → 'RE'. Only for the avatar on the sign-in screen."""
    words = [w for w in name.split() if w[:1].isalnum()]
    if not words:
        return "AD"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def validate(*, shop_name: str, owner_name: str, password: str, confirm: str,
             min_length: int) -> tuple[str, str]:
    shop_name, owner_name = (shop_name or "").strip(), (owner_name or "").strip()
    if not shop_name:
        raise SetupError("Type the shop's name — it goes on every receipt.")
    if not owner_name:
        raise SetupError("Type the owner's name. It's what they'll choose on the sign-in screen.")
    if len(shop_name) > NAME_MAX or len(owner_name) > NAME_MAX:
        raise SetupError(f"Names can be at most {NAME_MAX} characters.")
    try:
        auth_service.check_new_password(password, confirm, min_length=min_length)
    except auth_service.WeakPasswordError as exc:
        raise SetupError(str(exc)) from exc
    return shop_name, owner_name


def complete_setup(*, shop_name: str, owner_name: str, password: str, confirm: str,
                   min_length: int) -> User:
    """Create the first Admin and name the shop, in one transaction, exactly once."""
    shop_name, owner_name = validate(shop_name=shop_name, owner_name=owner_name,
                                     password=password, confirm=confirm,
                                     min_length=min_length)
    # What an Admin may do lives in the permission table, not in the role's name. A database
    # made without seeding it gave the first owner a Sukoon with no Khata, Insights or
    # Messages — found in the browser, not by a test. Idempotent and needed whatever happens
    # next, so it runs (and commits) before the claim rather than inside it.
    seed_permissions()
    try:
        # The claim comes first, and *that* is what makes this safe: the insert takes SQLite's
        # write lock before anyone counts users, so a second submission waits here, then finds
        # the owner already committed. Proven by breaking it — with the insert removed, the
        # two-thread test creates two owners 5 runs out of 5.
        # The rowcount check is a second layer that no SQLite test can separate from the first
        # (the lock already serialises writers); it's kept so this doesn't rest on one locking
        # subtlety if the transaction handling ever changes.
        claimed = db.session.execute(
            sqlite_insert(Setting)
            .values(key=SETUP_MARKER, value=utcnow().isoformat(), updated_at=utcnow())
            .on_conflict_do_nothing(index_elements=[Setting.key])
        ).rowcount
        if claimed != 1 or not needs_setup():
            raise SetupAlreadyDone("Sukoon has already been set up on this PC.")
        user = User(name=owner_name, initials=initials_for(owner_name), role=ROLE_ADMIN,
                    password_hash=auth_service.hash_password(password), is_active=True)
        db.session.add(user)
        settings_service.set(SHOP_NAME_KEY, shop_name)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user
