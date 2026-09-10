"""Sale, SaleItem, Payment (ADR-0016).

``discount_paisa`` / ``line_discount_paisa`` / ``tax_paisa`` exist as columns fixed
at zero in v1 (ADR-0008): no UI, service, or route may set them non-zero. Money is
integer paisa, quantity is integer milli-units.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

PAYMENT_METHODS = ("cash", "card", "credit")
SALE_STATUSES = ("completed", "refunded", "partially_refunded")
QUANTITY_SOURCES = (
    "stepper",
    "manual_weight",
    "manual_amount",
    "usb_scale",  # reserved (ADR-0005)
    "scale_label",  # reserved (ADR-0005)
)


class Sale(TimestampMixin, db.Model):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id"), nullable=True
    )  # NULL = walk-in
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    terminal_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subtotal_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_paisa: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_paisa: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_tendered_paisa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_paisa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    items: Mapped[list[SaleItem]] = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )


class SaleItem(db.Model):
    __tablename__ = "sale_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sale.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id"), nullable=False
    )
    product_barcode_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_barcode.id"), nullable=True
    )
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price_paisa_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_source: Mapped[str] = mapped_column(String(16), nullable=False)
    line_discount_paisa: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    line_total_paisa: Mapped[int] = mapped_column(Integer, nullable=False)

    sale: Mapped[Sale] = relationship(Sale, back_populates="items")


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id"), nullable=False
    )
    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sale.id"), nullable=True
    )
    amount_paisa: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
