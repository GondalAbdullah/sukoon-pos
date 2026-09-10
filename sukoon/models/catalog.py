"""Category, Product, ProductBarcode (ADR-0016).

Money is integer paisa; quantity is integer milli-units (thousandths of a unit) —
ADR-0004, ADR-0007. Column suffixes ``_paisa`` / ``_milli`` make the unit
unmissable. No floats, ever.
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sukoon.extensions import db
from sukoon.models.base import CreatedUpdatedMixin, TimestampMixin


class Category(db.Model):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(CreatedUpdatedMixin, db.Model):
    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("sell_price_paisa >= 0", name="sell_price_non_negative"),
        CheckConstraint(
            "cost_price_paisa IS NULL OR cost_price_paisa >= 0",
            name="cost_price_non_negative",
        ),
        CheckConstraint(
            "length(trim(name)) > 0", name="name_not_blank"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Tier A
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id"), nullable=True
    )
    unit_label: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unit"
    )
    allows_fractional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # ADR-0004: presentation/input only, never storage
    cost_price_paisa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sell_price_paisa: Mapped[int] = mapped_column(Integer, nullable=False)  # Tier A
    stock_quantity_milli: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    low_stock_threshold_milli: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = no low-stock check runs (ADR-0016)
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # ADR-0011: one or more Tier C fields unfilled
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )

    category: Mapped[Category | None] = relationship(Category)
    barcodes: Mapped[list[ProductBarcode]] = relationship(
        "ProductBarcode", back_populates="product", cascade="all, delete-orphan"
    )


class ProductBarcode(TimestampMixin, db.Model):
    __tablename__ = "product_barcode"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id"), nullable=False
    )
    barcode: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    price_override_paisa: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = fall back to product.sell_price_paisa
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )

    product: Mapped[Product] = relationship(Product, back_populates="barcodes")
