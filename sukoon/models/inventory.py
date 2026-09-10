"""StockMovement — the append-only audit trail behind every change to a product's
counted stock (ADR-0016). Quantities are signed milli-units (ADR-0004).
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

MOVEMENT_TYPES = ("stock_in", "stock_out", "correction", "sale", "refund")


class StockMovement(TimestampMixin, db.Model):
    __tablename__ = "stock_movement"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_delta_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
