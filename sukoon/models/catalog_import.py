"""A product spreadsheet upload and its staged rows (ADR-0043).

Rows wait here until the owner has decided about them; only "Add to stock" turns them into
products. The batch stays afterwards, as the record of what was imported and for undo.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin
from sukoon.models.catalog import Product

# ready: becomes a product on "Add to stock"; choose: one of a group of same-named rows that
# differ, waiting for the owner; needs_price: no selling price yet; skipped: left out, with a
# reason; imported: a product exists (product_id).
IMPORT_ROW_STATUSES = ("ready", "choose", "needs_price", "skipped", "imported")


class CatalogImport(TimestampMixin, db.Model):
    __tablename__ = "catalog_import"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    rows: Mapped[list[CatalogImportRow]] = relationship(
        "CatalogImportRow", back_populates="batch", cascade="all, delete-orphan",
        order_by="CatalogImportRow.line_no",
    )


class CatalogImportRow(db.Model):
    __tablename__ = "catalog_import_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_import.id"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)  # line in the uploaded file
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # the name lowercased with spaces collapsed: rows sharing it are one duplicate group
    group_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost_price_paisa: Mapped[int | None] = mapped_column(Integer, nullable=True)  # exact (ADR-0044)
    sell_price_paisa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    low_stock_threshold_milli: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # the file's figures exactly as written, shown if a third decimal had to be rounded
    source_cost: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_sell: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id"), nullable=True, index=True
    )

    batch: Mapped[CatalogImport] = relationship(CatalogImport, back_populates="rows")
    product: Mapped[Product | None] = relationship(Product)
