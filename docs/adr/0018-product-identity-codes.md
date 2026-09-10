# 0018 — Product Identity Codes (SKU generation + internal barcodes)

Status: **Accepted** 2026-09-10 — direction confirmed by the client
Date: 2026-09-10
Phase: 2
Depends on: [ADR-0009](0009-multiple-barcodes-per-product.md), [ADR-0010](0010-label-production.md), [ADR-0012](0012-product-field-requirements.md)
Resolves: O-17

## Context

Two identifier questions had to be settled before Phase 2 could build product
creation and barcode assignment:

1. **O-17 — does the shop use its own product codes (`sku`)?** ADR-0012 kept the
   column as `TEXT NULL UNIQUE` and parked the wider question: if Mr. Abdullah
   writes codes on shelf labels or supplier orders, a generated format should match
   what he already writes; if not, the column could be dropped or left empty.
2. **What symbology does Sukoon generate for goods with no manufacturer barcode?**
   ADR-0010 committed to generating labels but not to a code format. A generated
   code must never collide with a real manufacturer EAN-13.

## Decision

### 1. SKU is auto-generated, category-prefixed, and editable

Confirmed with the client: the shop wants a shelf/stock-taking code, in the style
already shown in the design mockups (`OIL-5021`, `GRN-1014`).

- On product create, Sukoon assigns `sku = "{PREFIX}-{NNNN}"`.
- `PREFIX` is derived from the product's category name: its letters, uppercased,
  first three (`Cooking Oils & Ghee` → `COO`). A product with **no category** —
  legal under ADR-0012 Tier C — gets `PREFIX = "GEN"`.
- `NNNN` is a shop-wide running number, zero-padded to four digits and allowed to
  grow past it, taken from a `setting` row (`sku.next_sequence`) incremented inside
  the same transaction that inserts the product. Shop-wide rather than per-prefix so
  the number alone is unique even if two categories derive the same prefix.
- The field is **editable by an Admin**. Auto-generation is a starting value, not a
  lock. Editing to a value already in use is rejected (`DuplicateSkuError`); the
  `UNIQUE` constraint from ADR-0016 is unchanged and is the backstop.
- The prefix does **not** retroactively change when a product's category changes.
  A SKU is a label that has been written on a shelf; silently renumbering it defeats
  its purpose. Changing it is a manual Admin edit.

The mock values (`OIL`, not `COO`, for Cooking Oils) are mock data, not a spec —
ADR-0006 makes the prototype authoritative for *style*, not for seed content.

### 2. Generated barcodes are Code 128 with an `SK-` prefix

For a product with no manufacturer barcode, "generate a barcode" produces
`SK-{NNNNNN}` (the `product_barcode` row's own id, zero-padded to six), encoded as
**Code 128**.

- Code 128 encodes letters and digits, so the human-readable `SK-000042` *is* the
  code — no separate mapping.
- The `SK-` prefix cannot be a valid EAN-13/UPC (those are digits only), so an
  internal code can never collide with a scanned manufacturer barcode, and the
  resolver chain (ADR-0009) needs no special case.
- Every commodity USB keyboard-wedge scanner reads Code 128. No 2D imager needed.
- QR was rejected: it needs a 2D imager the shop's 1D laser scanner is not.
- EAN-13 in the "2" in-store range was considered and rejected: it works, but it
  requires check-digit maths and produces a code visually indistinguishable from a
  real product's, for no gain here.

Barcode images are rendered with `python-barcode` (`Code128`, PNG via Pillow) and
laid onto the A4 sheet with ReportLab, exactly as ADR-0010 specified.

### 3. Where the new Phase 2 code lives (ADR-0003 clarification)

ADR-0003's module list, frozen at the Phase 0 gate, did not name a home for two
pieces of Phase 2 plumbing:

- **`services/receipts/labels.py`** — label-sheet PDF and barcode-image generation.
  Placed inside the existing `services/receipts/` package (the "produce a document
  to print" package), alongside the ESC/POS builder and PDF fallback it already
  owns. A file in a listed package, not a new top-level module.
- **`services/settings_service.py`** — a thin typed accessor (`get` / `set` /
  `get_int`) over the `setting` KV table from ADR-0016. This *is* a new module.
  It is recorded here rather than smuggled in: it owns one table's access the way
  `khata_service` owns the ledger's, it holds no policy, and the alternative —
  every service poking `Setting` rows directly — is the scattering ADR-0003 exists
  to prevent. Flagged in `context.md` §4b as a deliberate, minimal deviation from
  the frozen list.

## Alternatives Considered

- **Drop the `sku` column** — rejected; the client does want a shop code.
- **Manual, optional SKU with no generation** — rejected; it would mostly sit empty
  and the shop would have no consistent code, which is the thing they asked for.
- **Per-category SKU sequence** (`OIL-0001`, `OIL-0002`, `GRN-0001`) — rejected as
  more state to keep (a counter per category) for a cosmetic gain; a shop-wide
  number is simpler and still unique.
- **A `category.sku_prefix` column** so the prefix is explicit rather than derived —
  rejected for v1: it is a schema change against the just-frozen migration, to
  replace a rule (`first 3 letters`) that works. Revisit if a shop wants prefixes
  that do not match their category names.
- **Code 128 vs EAN-13 vs QR** — covered above.

## Consequences

**Easier:** every product has a consistent shelf code from the moment it is created,
with no cashier or Admin having to invent one. Internal barcodes are self-describing
and provably distinct from manufacturer codes.

**Harder:** SKU generation reads and writes a `setting` row inside the product-create
transaction — one more thing in that unit of work. Prefix derivation from a category
name is a heuristic that will occasionally produce an unlovely prefix; the Admin can
fix it by editing the field.

**Forecloses:** nothing. A `category.sku_prefix` column, a per-category sequence, or
a different symbology are all reachable later without disturbing existing data
(existing SKUs and barcodes are just strings).

## Consequential test cases

- A created product gets `sku` matching `^[A-Z]{2,3}-\d{4,}$`, unique, category-derived
- A product created with no category gets a `GEN-` SKU
- Two products whose categories derive the same prefix still get distinct SKUs
- Editing a SKU to an existing value is rejected; the DB `UNIQUE` is the backstop
- Changing a product's category does not change its existing SKU
- `generate_barcode` yields `SK-` + zero-padded id; the value is unique and Code128-encodable
- A generated barcode image decodes back to the code it was generated from (ADR-0010)
- An `SK-` code and a 13-digit EAN both resolve through one unchanged resolver chain
