"""CreditLedgerEntry — the authoritative record of every movement on a Khata
(ADR-0016, ADR-0014, ADR-0015). ``customer.balance_paisa`` is only a cache of this.

``override_authorised_by_user_id`` is populated only on an entry where an Admin
overrode a blocked credit sale (ADR-0014), recorded distinctly from the cashier who
rang it.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

LEDGER_ENTRY_TYPES = ("credit_sale", "payment", "refund", "adjustment")


class CreditLedgerEntry(TimestampMixin, db.Model):
    __tablename__ = "credit_ledger_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_paisa: Mapped[int] = mapped_column(Integer, nullable=False)  # signed
    balance_after_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sale.id"), nullable=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment.id"), nullable=True
    )
    override_authorised_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
