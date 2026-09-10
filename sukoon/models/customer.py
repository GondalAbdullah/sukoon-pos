"""Customer — a named person, with or without a Khata (ADR-0016, ADR-0013).

Phone duplicates are *flagged, not constrained* (ADR-0013): no unique constraint on
either phone column. ``phone_normalised`` is the matching/delivery key and is NULL
for an unparseable number, which excludes it from both.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

PHONE_VERIFIED_METHODS = ("shown", "called", "otp")


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_normalised: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credit_limit_paisa: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = limit unenforced (ADR-0014)
    credit_terms_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = overdue untracked (ADR-0015)
    balance_paisa: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # cache of the ledger; the ledger is authoritative
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    phone_verified_method: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    phone_verified_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
