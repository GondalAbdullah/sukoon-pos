"""Typed accessor over the ``setting`` key/value table (ADR-0016, ADR-0018 §3).

Holds no policy — every caller decides what a key means and what its default is.
Values are stored as text; the ``get_int`` helper parses on read.
"""
from __future__ import annotations

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from sukoon.extensions import db
from sukoon.models.base import utcnow
from sukoon.models.system import Setting


def get(key: str, default: str | None = None) -> str | None:
    row = db.session.get(Setting, key)
    return row.value if row is not None and row.value is not None else default


def get_int(key: str, default: int) -> int:
    raw = get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def set(key: str, value: str | int | None) -> None:
    """Insert-or-update in one statement. The earlier read-then-insert let two workers
    both see a key missing and both insert it — found by the Phase 5 concurrency test,
    when two workers paused the queue at the same instant. Doesn't commit; the caller's
    transaction does."""
    text = None if value is None else str(value)
    now = utcnow()
    db.session.execute(
        sqlite_insert(Setting)
        .values(key=key, value=text, updated_at=now)
        .on_conflict_do_update(index_elements=[Setting.key],
                               set_={"value": text, "updated_at": now})
    )
    # the Core statement bypasses the session's cached copy of this one row
    cached = db.session.identity_map.get(db.session.identity_key(Setting, key))
    if cached is not None:
        db.session.expire(cached)
