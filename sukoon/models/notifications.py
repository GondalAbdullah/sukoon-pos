"""NotificationQueue — the durable outbox for WhatsApp messages (ADR-0016;
Phase 5: ADR-0028–0033).

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

NOTIFICATION_TYPES = (
    "credit_sale",
    "statement",
    "overdue_reminder",
    "account_notice",   # ADR-0028
    "payment_receipt",  # ADR-0032
    "test",             # ADR-0033 §10 — an Admin's test send, no customer
)
# 'sending' = claimed by the worker (ADR-0033 §8); stuck there 10 minutes means the
# outcome is unknown and it is abandoned, never resent automatically (§9).
NOTIFICATION_STATUSES = ("pending", "sending", "sent", "failed", "abandoned")


class NotificationQueue(TimestampMixin, db.Model):
    __tablename__ = "notification_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id"), nullable=True
    )  # NULL only for a test send (ADR-0033 §10)
    notification_type: Mapped[str] = mapped_column(String(24), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    payload_json: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MessageDailyCount(db.Model):
    """Messages counted toward the daily cap, per shop-time day (ADR-0033 §4, §8).
    Incremented by one atomic ``WHERE sent < cap`` so two workers can't overshoot."""

    __tablename__ = "message_daily_count"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class StatementRun(db.Model):
    """Which months' WhatsApp statements were queued or skipped (ADR-0031 §2)."""

    __tablename__ = "statement_run"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
