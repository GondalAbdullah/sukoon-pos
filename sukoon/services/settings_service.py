"""Typed accessor over the ``setting`` key/value table (ADR-0016, ADR-0018 §3).

Holds no policy — every caller decides what a key means and what its default is.
Values are stored as text; the ``get_int`` helper parses on read.
"""
from __future__ import annotations

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
    row = db.session.get(Setting, key)
    text = None if value is None else str(value)
    if row is None:
        db.session.add(Setting(key=key, value=text, updated_at=utcnow()))
    else:
        row.value = text
        row.updated_at = utcnow()
