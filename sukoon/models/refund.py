"""Refund and RefundItem (ADR-0020).

Added in Phase 3 — the first migration since the Phase 1 schema freeze
(ADR-0016). A refund always references the original sale; it may cover part of it.
Nothing moves (no stock, no cash, no ledger entry) until an Admin approves a
``pending_approval`` refund. Money is integer paisa, quantity integer milli-units.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

REFUND_STATUSES = ("pending_approval", "approved", "rejected")
REFUND_METHODS = ("cash", "credit_ledger", "card")  # 'card' reserved (ADR-0020)


class Refund(TimestampMixin, db.Model):
    __tablename__ = "refund"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
        CheckConstraint("total_paisa >= 0", name="total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sale.id"), nullable=False)
    total_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    initiated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    items: Mapped[list[RefundItem]] = relationship(
        "RefundItem", back_populates="refund", cascade="all, delete-orphan"
    )


class RefundItem(db.Model):
    __tablename__ = "refund_item"
    __table_args__ = (
        CheckConstraint("quantity_milli > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey("refund.id"), nullable=False)
    sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_item.id"), nullable=False
    )
    quantity_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    restock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    refund: Mapped[Refund] = relationship(Refund, back_populates="items")
