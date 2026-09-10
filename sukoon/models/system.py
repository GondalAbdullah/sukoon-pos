"""InvoiceCounter and Setting (ADR-0016).

``invoice_counter`` is a single row (id = 1) carrying the current ``year`` and
``next_sequence``. The atomic claim-and-maybe-reset logic is Phase 3's; the policy
(reset to 1 on the first sale of a new calendar year) is fixed in ADR-0016.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sukoon.extensions import db
from sukoon.models.base import utcnow


class InvoiceCounter(db.Model):
    __tablename__ = "invoice_counter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    next_sequence: Mapped[int] = mapped_column(Integer, nullable=False)


class Setting(db.Model):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
