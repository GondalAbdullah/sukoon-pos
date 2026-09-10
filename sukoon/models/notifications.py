"""NotificationQueue — the durable outbox for WhatsApp messages (ADR-0016).

A secondary action never breaks a primary one (ADR-0003 §6): enqueuing here must
never raise into a sale transaction. ``dedupe_key`` is UNIQUE so the same event
cannot be queued twice.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

NOTIFICATION_TYPES = ("credit_sale", "statement", "overdue_reminder")
NOTIFICATION_STATUSES = ("pending", "sent", "failed", "abandoned")


class NotificationQueue(TimestampMixin, db.Model):
    __tablename__ = "notification_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(24), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    payload_json: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
