"""Inventory and product-management logic (Development Specification Phase 2).

No Flask import lives here (ADR-0003 §1). Every function takes plain values and
returns models or plain data; routes parse and render, this module decides.

Conventions (ADR-0003 §4):
* ``resolve_*``  — look something up
* ``compute_*`` / ``_prefix`` — pure calculation, no I/O
* ``validate_*`` — check before anything is trusted
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sukoon.extensions import db
from sukoon.models import (
    Category,
    Product,
    ProductBarcode,
    SaleItem,
    StockMovement,
)
from sukoon.services import settings_service

# --- named errors, per ADR-0003 §5 --------------------------------------------


class InventoryError(Exception):
    """Base for every inventory/catalog failure."""


class ValidationError(InventoryError):
    def __init__(self, message: str, *, field: str | None = None):
        self.field = field
        super().__init__(message)


class DuplicateSkuError(InventoryError):
    pass


class DuplicateBarcodeError(InventoryError):
    pass


class InsufficientStockError(InventoryError):
    """A stock-out or sale would drive the counted level below zero."""


class FractionalQuantityError(InventoryError):
    """A sealed-pack product (allows_fractional = 0) given a non-whole quantity."""


class ProductInUseError(InventoryError):
    """A hard delete was attempted on a product with movement or sale history."""


# --- money / quantity validation (ADR-0007, ADR-0004) -------------------------

_MILLI = 1000


def validate_whole_rupee(paisa: int, *, field: str) -> int:
    if paisa is None:
        raise ValidationError(f"{field} is required.", field=field)
    if paisa < 0:
        raise ValidationError(f"{field} cannot be negative.", field=field)
    if paisa % 100 != 0:
        raise ValidationError(
            f"{field} must be a whole number of rupees.", field=field
        )
    return paisa


def validate_quantity_milli(
    quantity_milli: int, *, allows_fractional: bool, field: str = "quantity"
) -> int:
    if quantity_milli is None:
        raise ValidationError("A quantity is required.", field=field)
    if not allows_fractional and quantity_milli % _MILLI != 0:
        raise FractionalQuantityError(
            "This item is sold as whole units and cannot take a fractional quantity."
        )
    return quantity_milli


# --- SKU generation (ADR-0018) ----------------------------------------------

_SKU_SEQ_KEY = "sku.next_sequence"
_PREFIX_RE = re.compile(r"[^A-Za-z]")


def compute_category_prefix(category: Category | None) -> str:
    """First three letters of the category name, uppercased; ``GEN`` if the
    product has no category (legal under ADR-0012 Tier C)."""
    if category is None:
        return "GEN"
    letters = _PREFIX_RE.sub("", category.name).upper()
    return (letters[:3] or "GEN")


def allocate_sku(category: Category | None) -> str:
    """``{PREFIX}-{NNNN}`` with a shop-wide running number. Reads and writes the
    counter in the same transaction as the caller's product insert."""
    seq = settings_service.get_int(_SKU_SEQ_KEY, 1)
    settings_service.set(_SKU_SEQ_KEY, seq + 1)
    return f"{compute_category_prefix(category)}-{seq:04d}"


# --- provisional state (ADR-0011, ADR-0012) --------------------------------

def compute_is_provisional(product: Product) -> bool:
    """Exactly 'one or more Tier C fields unfilled' (ADR-0012): cost price,
    category, or low-stock threshold."""
    return (
        product.cost_price_paisa is None
        or product.category_id is None
        or product.low_stock_threshold_milli is None
    )


# --- categories --------------------------------------------------------------

def list_categories(*, include_inactive: bool = False) -> list[Category]:
    stmt = db.select(Category)
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    return list(
        db.session.scalars(stmt.order_by(Category.display_order, Category.name))
    )


def create_category(name: str, *, display_order: int = 0) -> Category:
    clean = (name or "").strip()
    if not clean:
        raise ValidationError("A category name is required.", field="name")
    if db.session.scalar(
        db.select(Category).where(db.func.lower(Category.name) == clean.lower())
    ):
        raise ValidationError("A category with that name already exists.", field="name")
    category = Category(name=clean, display_order=display_order)
    db.session.add(category)
    db.session.commit()
    return category


def update_category(
    category: Category,
    *,
    name: str | None = None,
    display_order: int | None = None,
    is_active: bool | None = None,
) -> Category:
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValidationError("A category name is required.", field="name")
        category.name = clean
    if display_order is not None:
        category.display_order = display_order
    if is_active is not None:
        category.is_active = is_active
    db.session.commit()
    return category


# --- products ---------------------------------------------------------------

def get_product(product_id: int) -> Product | None:
    return db.session.get(Product, product_id)


def create_product(
    *,
    name: str,
    sell_price_paisa: int,
    cost_price_paisa: int | None = None,
    category: Category | None = None,
    unit_label: str = "unit",
    allows_fractional: bool = False,
    low_stock_threshold_milli: int | None = None,
    created_by_user_id: int | None = None,
    sku: str | None = None,
) -> Product:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("A product name is required.", field="name")

    validate_whole_rupee(sell_price_paisa, field="Selling price")
    if cost_price_paisa is not None:
        validate_whole_rupee(cost_price_paisa, field="Cost price")

    if sku is None:
        sku = allocate_sku(category)
    else:
        sku = sku.strip() or None
        if sku and _sku_taken(sku):
            raise DuplicateSkuError(f"SKU {sku} is already in use.")

    product = Product(
        name=clean_name,
        sku=sku,
        category_id=category.id if category else None,
        unit_label=(unit_label or "unit").strip() or "unit",
        allows_fractional=allows_fractional,
        cost_price_paisa=cost_price_paisa,
        sell_price_paisa=sell_price_paisa,
        low_stock_threshold_milli=low_stock_threshold_milli,
        created_by_user_id=created_by_user_id,
    )
    product.is_provisional = compute_is_provisional(product)
    db.session.add(product)
    _commit_translating_integrity()
    return product


def update_product(
    product: Product,
    *,
    name: str | None = None,
    sell_price_paisa: int | None = None,
    cost_price_paisa: int | None = ...,  # sentinel: ... means "not supplied"
    category_id: int | None = ...,
    unit_label: str | None = None,
    allows_fractional: bool | None = None,
    low_stock_threshold_milli: int | None = ...,
    sku: str | None = None,
) -> Product:
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValidationError("A product name is required.", field="name")
        product.name = clean
    if sell_price_paisa is not None:
        product.sell_price_paisa = validate_whole_rupee(
            sell_price_paisa, field="Selling price"
        )
    if cost_price_paisa is not ...:
        if cost_price_paisa is not None:
            validate_whole_rupee(cost_price_paisa, field="Cost price")
        product.cost_price_paisa = cost_price_paisa
    if category_id is not ...:
        product.category_id = category_id
    if unit_label is not None:
        product.unit_label = unit_label.strip() or "unit"
    if allows_fractional is not None:
        product.allows_fractional = allows_fractional
    if low_stock_threshold_milli is not ...:
        product.low_stock_threshold_milli = low_stock_threshold_milli
    if sku is not None:
        clean_sku = sku.strip() or None
        if clean_sku and clean_sku != product.sku and _sku_taken(clean_sku):
            raise DuplicateSkuError(f"SKU {clean_sku} is already in use.")
        product.sku = clean_sku

    product.is_provisional = compute_is_provisional(product)
    _commit_translating_integrity()
    return product


def delete_product(product: Product) -> str:
    """Soft-delete (deactivate) a product that has movement or sale history;
    hard-delete one that has none. Returns ``"soft"`` or ``"hard"`` (edge case:
    'deleting a product with sales history is a soft delete, not a hard delete')."""
    has_history = db.session.scalar(
        db.select(db.func.count())
        .select_from(SaleItem)
        .where(SaleItem.product_id == product.id)
    ) or db.session.scalar(
        db.select(db.func.count())
        .select_from(StockMovement)
        .where(StockMovement.product_id == product.id)
    )
    if has_history:
        product.is_active = False
        db.session.commit()
        return "soft"
    db.session.delete(product)
    db.session.commit()
    return "hard"


def list_products(
    *,
    query: str | None = None,
    category_id: int | None = None,
    needs_completing: bool = False,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Product], int]:
    stmt = db.select(Product)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if needs_completing:
        stmt = stmt.where(Product.is_provisional.is_(True))
    if query:
        q = query.strip()
        like = f"%{q}%"
        stmt = stmt.where(
            db.or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.id.in_(
                    db.select(ProductBarcode.product_id).where(
                        ProductBarcode.barcode == q
                    )
                ),
            )
        )
    total = db.session.scalar(
        db.select(db.func.count()).select_from(stmt.subquery())
    )
    rows = list(
        db.session.scalars(
            stmt.order_by(Product.name).limit(limit).offset(offset)
        )
    )
    return rows, int(total or 0)


def _sku_taken(sku: str) -> bool:
    return bool(
        db.session.scalar(db.select(Product.id).where(Product.sku == sku))
    )


def _commit_translating_integrity() -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        db.session.commit()
    except IntegrityError as exc:  # pragma: no cover - defensive; UNIQUE backstop
        db.session.rollback()
        text = str(exc.orig).lower()
        if "sku" in text:
            raise DuplicateSkuError("That SKU is already in use.") from exc
        if "barcode" in text:
            raise DuplicateBarcodeError("That barcode is already in use.") from exc
        raise


# --- stock movements (Development Spec Phase 2 step 3) ---------------------

_ADJUSTMENT_TYPES = {"stock_in", "stock_out", "correction"}


def apply_stock_movement(
    *,
    product: Product,
    movement_type: str,
    quantity_milli: int,
    reason: str,
    user_id: int,
    reference_type: str | None = None,
    reference_id: int | None = None,
    commit: bool = True,
) -> StockMovement:
    """Record one movement and update the product's counted level atomically.

    For ``stock_in`` / ``stock_out`` / ``sale`` / ``refund``, ``quantity_milli`` is
    a positive magnitude. For ``correction`` it is the *new counted level*, and the
    delta is derived (glossary: 'Correct count').

    ``commit=False`` adds the movement to the session but leaves the commit to the
    caller — how ``sales_service`` folds a whole cart's deductions into the single
    sale transaction (Development Spec Phase 3: 'all-or-nothing commit').
    """
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("A reason is required for every stock change.", field="reason")

    before = product.stock_quantity_milli

    if movement_type == "correction":
        if quantity_milli is None or quantity_milli < 0:
            raise ValidationError("A counted level cannot be negative.", field="quantity")
        validate_quantity_milli(
            quantity_milli, allows_fractional=product.allows_fractional
        )
        after = quantity_milli
        delta = after - before
        product.stock_quantity_milli = after
    elif movement_type in {"stock_in", "stock_out", "sale", "refund"}:
        if quantity_milli is None or quantity_milli <= 0:
            raise ValidationError("A quantity greater than zero is required.", field="quantity")
        validate_quantity_milli(
            quantity_milli, allows_fractional=product.allows_fractional
        )
        sign = 1 if movement_type in {"stock_in", "refund"} else -1
        delta = sign * quantity_milli
        # One atomic relative UPDATE, with the non-negative guard in the WHERE
        # clause. Two terminals deducting the same product in the same second
        # cannot lose an update or drive the count below zero — the read and the
        # write are one statement, not a read in Python then a write
        # (edge-case matrix: 'concurrent stock updates ... without lost updates').
        new_level = db.session.execute(
            db.update(Product)
            .where(
                Product.id == product.id,
                Product.stock_quantity_milli + delta >= 0,
            )
            .values(stock_quantity_milli=Product.stock_quantity_milli + delta)
            .returning(Product.stock_quantity_milli)
        ).scalar_one_or_none()
        db.session.expire(product)  # the Core UPDATE bypassed the ORM object
        if new_level is None:
            raise InsufficientStockError(
                f"Only {product.stock_quantity_milli / _MILLI:g} "
                f"{product.unit_label} in stock."
            )
        after = new_level
        before = after - delta
    else:
        raise ValidationError(f"Unknown movement type: {movement_type}")

    movement = StockMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity_delta_milli=delta,
        quantity_before_milli=before,
        quantity_after_milli=after,
        reason=clean_reason,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by_user_id=user_id,
    )
    db.session.add(movement)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return movement


def movements_for_product(product_id: int, *, limit: int = 50) -> list[StockMovement]:
    return list(
        db.session.scalars(
            db.select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(limit)
        )
    )


# --- low-stock alerting (Development Spec Phase 2 step 4) -----------------

def compute_stock_status(product: Product) -> str:
    """``out`` at or below zero, ``low`` at or below a set threshold, else
    ``healthy``. Threshold NULL disables the check entirely (ADR-0016)."""
    if product.stock_quantity_milli <= 0:
        return "out"
    if (
        product.low_stock_threshold_milli is not None
        and product.stock_quantity_milli <= product.low_stock_threshold_milli
    ):
        return "low"
    return "healthy"


def low_stock_products() -> list[Product]:
    """Active products at or below their threshold, or out of stock. Fires
    exactly at the boundary (``<=``)."""
    stmt = db.select(Product).where(
        Product.is_active.is_(True),
        db.or_(
            Product.stock_quantity_milli <= 0,
            db.and_(
                Product.low_stock_threshold_milli.is_not(None),
                Product.stock_quantity_milli <= Product.low_stock_threshold_milli,
            ),
        ),
    )
    rows = list(db.session.scalars(stmt))
    rows.sort(key=lambda p: (p.stock_quantity_milli > 0, p.stock_quantity_milli))
    return rows


def catalog_summary() -> dict:
    products = list(
        db.session.scalars(db.select(Product).where(Product.is_active.is_(True)))
    )
    stock_value_paisa = sum(
        (p.cost_price_paisa or 0) * p.stock_quantity_milli // _MILLI for p in products
    )
    statuses = [compute_stock_status(p) for p in products]
    return {
        "catalog_size": len(products),
        "stock_value_paisa": stock_value_paisa,
        "needs_attention": sum(1 for s in statuses if s in {"low", "out"}),
        "out_of_stock": sum(1 for s in statuses if s == "out"),
    }


# --- barcodes (ADR-0009, ADR-0018) --------------------------------------------

@dataclass
class BarcodeMatch:
    product: Product
    product_barcode: ProductBarcode
    unit_price_paisa: int


def resolve_barcode(code: str) -> BarcodeMatch | None:
    """The resolver chain from ADR-0009/0005:
    1. an active ``product_barcode`` exact match  -> product + effective price
    2. registered code parsers                    -> empty in v1
    3. nothing                                     -> None (a calm not-found)
    """
    clean = (code or "").strip()
    if not clean:
        return None
    row = db.session.scalar(
        db.select(ProductBarcode).where(
            ProductBarcode.barcode == clean, ProductBarcode.is_active.is_(True)
        )
    )
    if row is None:
        return None
    product = db.session.get(Product, row.product_id)
    price = (
        row.price_override_paisa
        if row.price_override_paisa is not None
        else product.sell_price_paisa
    )
    return BarcodeMatch(product=product, product_barcode=row, unit_price_paisa=price)


def barcode_exists(code: str) -> bool:
    return bool(
        db.session.scalar(
            db.select(ProductBarcode.id).where(ProductBarcode.barcode == (code or "").strip())
        )
    )


def assign_barcode(
    *,
    product: Product,
    code: str,
    user_id: int,
    price_override_paisa: int | None = None,
    label: str | None = None,
) -> ProductBarcode:
    """Attach an existing (manufacturer) code to a product.

    Creating a row with a ``price_override_paisa`` is a destructive, Admin-only,
    step-up-protected action (ADR-0009) — the *route* enforces that; this function
    only records what it is given.
    """
    clean = (code or "").strip()
    if not clean:
        raise ValidationError("A barcode is required.", field="barcode")
    if barcode_exists(clean):
        raise DuplicateBarcodeError(f"Barcode {clean} is already assigned.")
    if price_override_paisa is not None:
        validate_whole_rupee(price_override_paisa, field="Override price")

    row = ProductBarcode(
        product_id=product.id,
        barcode=clean,
        price_override_paisa=price_override_paisa,
        label=(label or None),
        created_by_user_id=user_id,
    )
    db.session.add(row)
    _commit_translating_integrity()
    return row


def generate_barcode(*, product: Product, user_id: int) -> ProductBarcode:
    """Mint an internal Code 128 barcode (``SK-`` + the row's own zero-padded id)
    for a product that has none from a manufacturer (ADR-0018 §2)."""
    row = ProductBarcode(
        product_id=product.id,
        barcode="",  # filled once we have an id
        created_by_user_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    row.barcode = f"SK-{row.id:06d}"
    db.session.commit()
    return row


def deactivate_barcode(barcode_row: ProductBarcode) -> None:
    """Ending a promo / retiring a label is ``is_active = 0``; the row is never
    deleted because historical sale lines reference it (ADR-0009)."""
    barcode_row.is_active = False
    db.session.commit()


def barcodes_for_product(product_id: int) -> list[ProductBarcode]:
    return list(
        db.session.scalars(
            db.select(ProductBarcode)
            .where(ProductBarcode.product_id == product_id)
            .order_by(ProductBarcode.created_at, ProductBarcode.id)
        )
    )
