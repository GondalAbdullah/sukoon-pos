"""Shared model helpers. Models carry shape and constraints only (ADR-0003);
no business logic lives here.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone-aware UTC now, used as a column default."""
    return datetime.now(UTC)


class TimestampMixin:
    """A `created_at` every table in ADR-0016 carries, plus an `updated_at` for
    the tables that track mutation."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )


class CreatedUpdatedMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
