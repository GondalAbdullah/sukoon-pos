"""Importing a product spreadsheet (ADR-0043).

Upload → staged rows → the owner's decisions → "Add to stock" → products, then the worklist
where barcodes are scanned on and figures corrected. No Flask import (ADR-0003 §1).

The file format is Sukoon's own (``scripts/prepare_product_import.py`` writes it): columns
``Name, Category, Cost Price, Selling Price, Low Stock Level``; only Name and Selling Price
are required, and header case and spacing don't matter.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sukoon.extensions import db
from sukoon.models import (
    CatalogImport,
    CatalogImportRow,
    Category,
    Product,
    ProductBarcode,
    SaleItem,
    StockMovement,
)
from sukoon.services import inventory_service as inv
from sukoon.services import settings_service

# --- errors ---------------------------------------------------------------------------


class ImportFileError(inv.InventoryError):
    """The upload can't be read as a product list at all."""


# --- reading the file (pure) -----------------------------------------------------------

_SPACES = re.compile(r"\s+")
_ABSURD_PAISA = 1_000_000 * 100  # a million rupees or more is a barcode in the wrong column
_COLUMNS = {
    "name": "name",
    "category": "category",
    "cost price": "cost",
    "selling price": "sell",
    "low stock level": "low",
}
MAX_ROWS = 20_000


def tidy(text: str | None) -> str:
    return _SPACES.sub(" ", (text or "").strip())


def compute_group_key(name: str) -> str:
    return tidy(name).lower()


def compute_price_paisa(raw: str | None) -> int | None:
    """A money figure from the file as exact paisa (ADR-0044: paisa is kept, not rounded away),
    or ``None`` for unknown: blank, unreadable, negative, zero, or so large it is really a
    barcode. Only a third decimal (``1594.233``) is rounded, half-up, to the paisa."""
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        paisa = int((Decimal(text) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None
    if paisa <= 0 or paisa >= _ABSURD_PAISA:
        return None
    return paisa


def compute_threshold_milli(raw: str | None) -> int | None:
    try:
        value = int(Decimal((raw or "").strip()))
    except (InvalidOperation, ValueError):
        return None
    return value * 1000 if value >= 0 else None


def decode_upload(data: bytes) -> str:
    """UTF-8 (with or without Excel's byte-order mark); Windows-1252 if a file was saved by an
    older Excel. Never fails on a stray byte — a mangled character beats a refused file."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


@dataclass(frozen=True)
class ParsedRow:
    line_no: int
    name: str
    category: str | None
    cost_price_paisa: int | None
    sell_price_paisa: int | None
    low_stock_threshold_milli: int | None
    source_cost: str | None
    source_sell: str | None

    def same_values(self, other: ParsedRow) -> bool:
        return (
            (self.category or "").lower() == (other.category or "").lower()
            and self.cost_price_paisa == other.cost_price_paisa
            and self.sell_price_paisa == other.sell_price_paisa
            and self.low_stock_threshold_milli == other.low_stock_threshold_milli
        )


def parse_rows(text: str) -> list[ParsedRow]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        raise ImportFileError("The file is empty.")
    index: dict[str, int] = {}
    for i, col in enumerate(header):
        key = _COLUMNS.get(tidy(col).lower())
        if key and key not in index:
            index[key] = i
    missing = [label for label, key in (("Name", "name"), ("Selling Price", "sell"))
               if key not in index]
    if missing:
        raise ImportFileError(
            "This doesn't look like a Sukoon product file: no "
            + " or ".join(f"“{m}”" for m in missing) + " column. The columns are "
            "Name, Category, Cost Price, Selling Price, Low Stock Level.")

    def cell(record: list[str], key: str) -> str:
        i = index.get(key)
        return record[i] if i is not None and i < len(record) else ""

    rows: list[ParsedRow] = []
    for line_no, record in enumerate(reader, start=2):
        if not any(c.strip() for c in record):
            continue  # blank line
        if len(rows) >= MAX_ROWS:
            raise ImportFileError(f"The file has more than {MAX_ROWS:,} products.")
        cost_raw, sell_raw = cell(record, "cost").strip(), cell(record, "sell").strip()
        rows.append(ParsedRow(
            line_no=line_no,
            name=tidy(cell(record, "name"))[:255],
            category=tidy(cell(record, "category"))[:120] or None,
            cost_price_paisa=compute_price_paisa(cost_raw),
            sell_price_paisa=compute_price_paisa(sell_raw),
            low_stock_threshold_milli=compute_threshold_milli(cell(record, "low")),
            source_cost=cost_raw[:32] or None,
            source_sell=sell_raw[:32] or None,
        ))
    if not rows:
        raise ImportFileError("The file has a header but no products.")
    return rows


def compute_initial_statuses(rows: list[ParsedRow]) -> list[tuple[str, str | None]]:
    """(status, skip_reason) per row, in order (ADR-0043 §2). Same-named rows that are
    identical collapse onto the first; same-named rows that differ wait for the owner."""
    out: list[tuple[str, str | None]] = [("", None)] * len(rows)
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if not r.name:
            out[i] = ("skipped", "No name")
            continue
        groups[compute_group_key(r.name)].append(i)
    for members in groups.values():
        first = rows[members[0]]
        if len(members) > 1 and not all(first.same_values(rows[i]) for i in members[1:]):
            for i in members:
                out[i] = ("choose", None)
            continue
        out[members[0]] = _priced_status(first.sell_price_paisa)
        for i in members[1:]:
            out[i] = ("skipped", f"Same as line {first.line_no}")
    return out


def _priced_status(sell_price_paisa: int | None) -> tuple[str, None]:
    return ("needs_price" if sell_price_paisa is None else "ready", None)


def compute_cost_above_price(row) -> bool:
    return (row.cost_price_paisa is not None and row.sell_price_paisa is not None
            and row.cost_price_paisa > row.sell_price_paisa)


def compute_cost_was_rounded(row) -> bool:
    if row.source_cost is None or row.cost_price_paisa is None:
        return False
    try:
        return Decimal(row.source_cost.replace(",", "")) * 100 != row.cost_price_paisa
    except InvalidOperation:
        return False


# --- the batch ---------------------------------------------------------------------------

def create_import(*, filename: str, data: bytes, user_id: int) -> CatalogImport:
    rows = parse_rows(decode_upload(data))
    batch = CatalogImport(filename=(filename or "products.csv")[:255],
                          created_by_user_id=user_id)
    db.session.add(batch)
    for parsed, (status, reason) in zip(rows, compute_initial_statuses(rows), strict=True):
        batch.rows.append(CatalogImportRow(
            line_no=parsed.line_no,
            name=parsed.name or "(no name)",
            group_key=compute_group_key(parsed.name),
            category_name=parsed.category,
            cost_price_paisa=parsed.cost_price_paisa,
            sell_price_paisa=parsed.sell_price_paisa,
            low_stock_threshold_milli=parsed.low_stock_threshold_milli,
            source_cost=parsed.source_cost,
            source_sell=parsed.source_sell,
            status=status,
            skip_reason=reason,
        ))
    db.session.commit()
    return batch


def list_imports() -> list[CatalogImport]:
    return list(db.session.scalars(
        db.select(CatalogImport).order_by(CatalogImport.created_at.desc(), CatalogImport.id.desc())
    ))


def get_import(import_id: int) -> CatalogImport | None:
    return db.session.get(CatalogImport, import_id)


def get_row(batch: CatalogImport, row_id: int) -> CatalogImportRow | None:
    row = db.session.get(CatalogImportRow, row_id)
    return row if row is not None and row.import_id == batch.id else None


def _rows(batch: CatalogImport, *statuses: str):
    stmt = db.select(CatalogImportRow).where(CatalogImportRow.import_id == batch.id)
    if statuses:
        stmt = stmt.where(CatalogImportRow.status.in_(statuses))
    return db.session.scalars(stmt.order_by(CatalogImportRow.line_no))


def compute_summary(batch: CatalogImport) -> dict:
    counts = dict(db.session.execute(
        db.select(CatalogImportRow.status, db.func.count())
        .where(CatalogImportRow.import_id == batch.id)
        .group_by(CatalogImportRow.status)
    ).all())
    groups = db.session.scalar(
        db.select(db.func.count(db.distinct(CatalogImportRow.group_key)))
        .where(CatalogImportRow.import_id == batch.id, CatalogImportRow.status == "choose")
    )
    return {
        "total": sum(counts.values()),
        "ready": counts.get("ready", 0),
        "choose_rows": counts.get("choose", 0),
        "choose_groups": int(groups or 0),
        "needs_price": counts.get("needs_price", 0),
        "skipped": counts.get("skipped", 0),
        "imported": counts.get("imported", 0),
    }


def groups_to_choose(batch: CatalogImport) -> list[list[CatalogImportRow]]:
    groups: dict[str, list[CatalogImportRow]] = {}
    for row in _rows(batch, "choose"):
        groups.setdefault(row.group_key, []).append(row)
    return list(groups.values())


def rows_with_status(batch: CatalogImport, status: str) -> list[CatalogImportRow]:
    return list(_rows(batch, status))


def ready_rows_flagged(batch: CatalogImport) -> list[CatalogImportRow]:
    """Ready rows whose cost is above their price — imported as "Needs completing"."""
    return [r for r in _rows(batch, "ready") if compute_cost_above_price(r)]


# --- the owner's decisions ---------------------------------------------------------------

def choose_from_group(batch: CatalogImport, group_key: str, keep_row_ids: set[int]) -> int:
    """Keep the ticked rows of one undecided group, skip the rest. Returns how many were kept."""
    members = [r for r in _rows(batch, "choose") if r.group_key == group_key]
    if not members:
        raise inv.ValidationError("That group has already been decided.")
    kept = [r for r in members if r.id in keep_row_ids]
    lines = ", ".join(str(r.line_no) for r in kept)
    for r in members:
        if r in kept:
            r.status, r.skip_reason = _priced_status(r.sell_price_paisa)
        else:
            r.status = "skipped"
            r.skip_reason = f"Not kept — you kept line {lines}" if kept else "Not kept"
    db.session.commit()
    return len(kept)


def set_row_price(row: CatalogImportRow, sell_price_paisa: int | None) -> None:
    if row.status != "needs_price":
        raise inv.ValidationError("That row already has a price.")
    if sell_price_paisa is None or sell_price_paisa <= 0:
        raise inv.ValidationError("Enter a selling price above Rs 0.", field="sell_price")
    row.sell_price_paisa = inv.validate_price(sell_price_paisa, field="Selling price")
    row.status = "ready"
    db.session.commit()


def skip_row(row: CatalogImportRow) -> None:
    if row.status == "imported":
        raise inv.ValidationError("That row is already a product.")
    row.status, row.skip_reason = "skipped", "Skipped by you"
    db.session.commit()


def restore_row(row: CatalogImportRow) -> None:
    if row.status != "skipped":
        raise inv.ValidationError("Only a skipped row can be brought back.")
    if not row.name or row.name == "(no name)":
        raise inv.ValidationError("A row with no name can't be imported.")
    row.status, row.skip_reason = _priced_status(row.sell_price_paisa)
    db.session.commit()


# --- turning rows into products ------------------------------------------------------------

def add_ready_to_stock(batch: CatalogImport, *, user_id: int) -> int:
    """Every ready row becomes a product, in one transaction: all or nothing (ADR-0043 §2/§3).

    Written for thousands of rows at once: the SKU counter is read and written once (the same
    numbering ``inventory_service.allocate_sku`` gives, ADR-0018), and products are flushed
    together rather than one by one."""
    rows = list(_rows(batch, "ready"))
    if not rows:
        return 0
    try:
        categories = {c.name.lower(): c for c in db.session.scalars(db.select(Category))}
        for name in {r.category_name for r in rows if r.category_name}:
            if name.lower() not in categories:
                categories[name.lower()] = Category(name=name)
                db.session.add(categories[name.lower()])
        db.session.flush()  # new categories' ids, before products point at them

        seq = settings_service.get_int(inv.SKU_SEQ_KEY, 1)
        for row in rows:
            category = categories.get(row.category_name.lower()) if row.category_name else None
            product = Product(
                name=row.name,
                sku=f"{inv.compute_category_prefix(category)}-{seq:04d}",
                category_id=category.id if category is not None else None,
                cost_price_paisa=row.cost_price_paisa,
                sell_price_paisa=row.sell_price_paisa,
                low_stock_threshold_milli=row.low_stock_threshold_milli,
                created_by_user_id=user_id,
            )
            seq += 1
            product.is_provisional = (inv.compute_is_provisional(product)
                                      or compute_cost_above_price(row))
            row.product = product
            row.status, row.skip_reason = "imported", None
        settings_service.set(inv.SKU_SEQ_KEY, seq)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(rows)


def undo_import(batch: CatalogImport) -> tuple[int, int]:
    """Delete the batch's products that have never been sold or counted; deactivate the rest
    (the ordinary delete rule). Rows of deleted products go back to waiting. Returns
    (deleted, deactivated)."""
    product_ids = list(db.session.scalars(
        db.select(CatalogImportRow.product_id).where(
            CatalogImportRow.import_id == batch.id, CatalogImportRow.status == "imported",
            CatalogImportRow.product_id.is_not(None))))
    used: set[int] = set()
    for chunk in _chunks(product_ids):
        used |= set(db.session.scalars(
            db.select(SaleItem.product_id).where(SaleItem.product_id.in_(chunk))))
        used |= set(db.session.scalars(
            db.select(StockMovement.product_id).where(StockMovement.product_id.in_(chunk))))
    unused = [pid for pid in product_ids if pid not in used]
    back_to_waiting = db.case((CatalogImportRow.sell_price_paisa.is_(None), "needs_price"),
                              else_="ready")
    try:
        for chunk in _chunks(unused):
            db.session.execute(
                db.update(CatalogImportRow)
                .where(CatalogImportRow.import_id == batch.id,
                       CatalogImportRow.product_id.in_(chunk))
                .values(product_id=None, status=back_to_waiting, skip_reason=None),
                execution_options={"synchronize_session": False})
            db.session.execute(db.delete(ProductBarcode).where(ProductBarcode.product_id.in_(chunk)))
            db.session.execute(db.delete(Product).where(Product.id.in_(chunk)))
        for chunk in _chunks(sorted(used)):
            db.session.execute(db.update(Product).where(Product.id.in_(chunk))
                               .values(is_active=False))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    db.session.expire_all()
    return len(unused), len(used)


def _chunks(ids: list[int], size: int = 500):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


# --- the worklist ------------------------------------------------------------------------

WORKLIST_FILTERS = ("no_barcode", "needs_completing", "all")


def _has_barcode():
    return db.exists().where(ProductBarcode.product_id == Product.id,
                             ProductBarcode.is_active.is_(True))


def list_worklist(batch: CatalogImport, *, show: str = "no_barcode", query: str | None = None,
                  limit: int = 25, offset: int = 0
                  ) -> tuple[list[tuple[CatalogImportRow, Product]], int]:
    stmt = (db.select(CatalogImportRow, Product)
            .join(Product, Product.id == CatalogImportRow.product_id)
            .where(CatalogImportRow.import_id == batch.id, Product.is_active.is_(True)))
    if show == "no_barcode":
        stmt = stmt.where(~_has_barcode())
    elif show == "needs_completing":
        stmt = stmt.where(Product.is_provisional.is_(True))
    if query and query.strip():
        stmt = stmt.where(Product.name.ilike(f"%{query.strip()}%"))
    total = db.session.scalar(db.select(db.func.count()).select_from(stmt.subquery()))
    rows = db.session.execute(
        stmt.order_by(CatalogImportRow.line_no).limit(limit).offset(offset)).all()
    return [(r, p) for r, p in rows], int(total or 0)


def compute_worklist_counts(batch: CatalogImport) -> dict:
    base = (db.select(db.func.count()).select_from(CatalogImportRow)
            .join(Product, Product.id == CatalogImportRow.product_id)
            .where(CatalogImportRow.import_id == batch.id, Product.is_active.is_(True)))
    return {
        "all": db.session.scalar(base) or 0,
        "no_barcode": db.session.scalar(base.where(~_has_barcode())) or 0,
        "needs_completing": db.session.scalar(base.where(Product.is_provisional.is_(True))) or 0,
    }


def save_worklist_product(product: Product, *, name: str | None, category_id: int | None,
                          cost_price_paisa: int | None, sell_price_paisa: int | None,
                          low_stock_threshold_milli: int | None, barcode: str | None,
                          user_id: int, stock_milli: int | None = None) -> ProductBarcode | None:
    """One worklist row saved: the figures, the shelf count, then the scanned barcode. A barcode
    that belongs to another product is refused before anything is changed. The caller has
    already checked permission and step-up for a changed selling price (ADR-0008).

    ``stock_milli`` is what is on the shelf now. If it differs from Sukoon's level it is
    recorded as a count (a ``correction`` movement) — since ADR-0047 nothing can be sold until
    it has stock, so scanning an item on and counting it are one motion."""
    code = (barcode or "").strip()
    if code:
        match = db.session.scalar(db.select(ProductBarcode).where(ProductBarcode.barcode == code))
        if match is not None:
            if match.product_id == product.id:
                code = ""  # scanned twice onto the same product: nothing to do
            else:
                owner = db.session.get(Product, match.product_id)
                raise inv.DuplicateBarcodeError(
                    f"Barcode {code} already belongs to {owner.name}.")
    if category_id is not None and db.session.get(Category, category_id) is None:
        raise inv.ValidationError("Choose a category from the list.", field="category_id")
    if stock_milli is not None:
        if stock_milli < 0:
            raise inv.ValidationError("Stock can't be negative.", field="stock")
        inv.validate_quantity_milli(stock_milli, allows_fractional=product.allows_fractional,
                                    field="stock")
    inv.update_product(
        product,
        name=name,
        sell_price_paisa=sell_price_paisa,
        cost_price_paisa=cost_price_paisa,
        category_id=category_id,
        low_stock_threshold_milli=low_stock_threshold_milli,
    )
    if stock_milli is not None and stock_milli != product.stock_quantity_milli:
        inv.apply_stock_movement(product=product, movement_type="correction",
                                 quantity_milli=stock_milli,
                                 reason="Counted on the import worklist", user_id=user_id)
    if code:
        return inv.assign_barcode(product=product, code=code, user_id=user_id)
    return None


def product_has_barcode(product: Product) -> bool:
    return any(b.is_active for b in product.barcodes)
