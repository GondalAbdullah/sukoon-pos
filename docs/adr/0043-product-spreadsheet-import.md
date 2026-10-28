# 0043 — Importing the Shop's Product Spreadsheet

Status: **Accepted**
Amended by: [ADR-0044](0044-paisa-in-product-prices.md) (2026-10-28) — §3: the file's paisa are kept exactly, not rounded to the rupee
Date: 2026-10-28
Phase: post-release (1.2.0)
Depends on: [ADR-0007](0007-money-rounding.md), [ADR-0008](0008-authentication-and-access-control.md), [ADR-0011](0011-catalog-onboarding.md), [ADR-0012](0012-product-field-requirements.md), [ADR-0019](0019-phase-2-authorization.md)
Amends: [ADR-0011](0011-catalog-onboarding.md) §4 ("No CSV importer is built")
Resolves: O-28

## Context

ADR-0011 §4 declined to build an importer until the client produced a real file. He has:
`Grocery_Items_list.csv`, an OpenSourcePOS export of 8,116 rows. The owner is tired of entering
products by hand.

What the file actually holds, measured rather than assumed:

- **Name, category, cost, selling price, reorder level.** Usable.
- **Barcodes: destroyed.** 6,731 rows show Excel's scientific notation (`8.96E+12`); the digits
  are gone from the file. 198 are empty, ~400 are shop codes, ~780 survived. Not usable as a set.
- **No stock counts.** `location_stock` is empty in every row.
- **Duplicates.** 280 names appear more than once. In 108 groups every copy is identical; in 172
  groups (383 rows) the copies differ in price, cost, category or reorder level.
- **Bad values.** 51 rows have no selling price, 79 no cost, 7 cost above the selling price,
  3 a cost that is really a barcode (`8.96E+12`). 4 rows have a barcode where the name should be,
  and one is called `test`.
- **2,955 costs carry paisa** (`4.30`, `1594.23`) — OpenSourcePOS keeps an average cost. No
  selling price does.
- **261 category spellings** (`Shampoo`, `shampoo`, `Shamapoo`).

## Decision

### 1. Two steps: a cleaned spreadsheet, then an import inside Sukoon

`scripts/prepare_product_import.py` turns the OpenSourcePOS export into Sukoon's own import
format. It is run once by the developer, not by the shop.

- Columns: `Name, Category, Cost Price, Selling Price, Low Stock Level`. **No barcode column** —
  the barcodes in the source are not trustworthy, and a wrong barcode is worse than none: it
  rings up the wrong product.
- Spaces trimmed and collapsed. Rows that are not products are dropped and listed: a blank name,
  a name that is a number (`7.70E+11`), and `test`.
- A cost or price of a million rupees or more is a barcode in the wrong column → left blank.
- A cost of zero is left blank — unknown, never zero (ADR-0011).
- An optional category table (`docs/import/category-mapping.csv`, `correct_category` filled in by
  the developer) renames categories. Blank entries keep the file's spelling.
- Everything else, including duplicates and paisa, is kept as found. Deciding about those is the
  owner's job on the review screen, not the script's.

The importer accepts that format from any source, so a later supplier list works the same way.

### 2. Upload lands in a staging area, not in the catalog

**Stock → Import** (Admin, `catalog.manage`) takes a CSV and writes one `catalog_import_row` per
line under a `catalog_import` batch. **Nothing becomes a product yet.** The review screen shows:

- **Ready** — will become a product.
- **Choose which to keep** — a group of rows with the same name (case and spaces ignored) that
  differ. The owner ticks the copies to keep, one decision per group. Nothing in a group is
  imported until he has decided it (the developer's decision, 2026-10-23).
- **Identical copies** are collapsed without asking: the first is kept, the rest are skipped with
  the reason shown. Asking 108 times about rows that cannot be told apart is not a decision.
- **Needs a selling price** — a product cannot exist without one (ADR-0012 Tier A; Rs 0 would
  sell it free at the till). The owner types the price, or skips the row.
- **Skipped** — with the reason, and a way to bring any row back.

**Add to stock** turns every ready, undecided-free row into a product in one transaction: all or
nothing. Rows still waiting stay in the batch and can be added later, so the owner is never
forced to finish 172 decisions before the shop gets anything.

### 3. What an imported product looks like

- Category: matched to an existing one ignoring case, otherwise created.
- **Cost with paisa is rounded half-up to the rupee** (ADR-0007's invariant: every stored money
  value is whole rupees; half-up is the rule ADR-0007 already uses). The file's original figure is
  kept on the import row and shown beside the product on the worklist, so `4.30 → Rs 4` is never
  silent. Cost only drives *estimated* profit (ADR-0034), and the rounding is at most 50 paisa.
- No cost, no category, or no low-stock level → provisional ("Needs completing"), as ADR-0011 §3.
- **Cost above selling price → also provisional**, though every field is filled: the developer
  decided on 2026-10-23 that rows which look wrong are imported as "Needs completing", not
  skipped. Saving the product through any edit clears the flag (ADR-0011: completing one is an
  ordinary edit).
- Stock starts at zero, as the file has no counts. Stock comes from a count, recorded as a
  movement, never invented here.
- An SKU is allocated as for any product (ADR-0018).

### 4. The worklist: scan, correct, next

**Stock → Import → Work through products** lists the batch's products, filtered to *no barcode
yet* by default, with search. Each row is one inline form: **barcode, name, category, cost,
selling price, low-stock level**, saved with Enter.

The motion is the one ADR-0011 §1 chose: search a few letters, click the barcode box, scan the
item (the scanner sends Enter), and the row is saved and leaves the *no barcode yet* list.

- A barcode already on another product is refused, naming that product.
- **Changing a selling price still needs `product.edit_price` and the password re-entered**
  (ADR-0008 §5). The row has a password box that is only checked when the price changed. Importing
  is not a reason to weaken the one control on prices; the first import sets prices the same way
  bulk entry does (`catalog.manage`), every later change is an edit.

### 5. Undo

A batch can be **undone**: its products with no sales or stock movements are deleted; any with
history are deactivated (the existing delete rule); the rows go back to staging. A one-click
import of thousands of products into a live shop needs a one-click way back.

## Alternatives Considered

- **Creating products directly from the upload, no staging** — rejected. The 51 rows without a
  price cannot become products, and duplicate decisions would have to be made by deleting
  products afterwards, one at a time.
- **Keeping the surviving barcodes** — rejected for now. ~780 look intact, but there is no way to
  tell an intact 13-digit code from one Excel already mangled differently, and a wrong code sells
  the wrong item. Revisit with a fresh export straight from OpenSourcePOS.
- **Rounding cost down, or keeping paisa** — rejected. Paisa breaks ADR-0007's tested invariant;
  rounding down would quietly lower every cost. Half-up matches the rest of Sukoon.
- **A step-up-free price edit on the worklist** — rejected (§4).
- **Excel `.xlsx` upload** — not now. The shop's file is CSV, and CSV needs no new dependency.

## Consequences

**Easier:** the catalog goes from hand-entry to a morning's review and then scanning shelf by
shelf. Products are sellable from the moment they are added (by a unique name at the till) and
fully scannable once their barcode is attached.

**Harder:** two new tables, kept after the import for its record and for undo. Until barcodes are
attached, a cashier must type a name unique enough for the till to find one product.

**Not done here, noted:** at the till, an unknown scan could first offer "Is this one of these
imported products?" before the provisional-product form (the session-37 proposal). Left for a
later change.

## Consequential test cases

- The prepare script drops barcodes, junk rows and barcode-in-cost values, and applies the
  category table
- An upload creates rows only, no products
- Identical duplicates collapse; differing ones wait for a choice and are not imported until made
- A row without a selling price cannot be added until priced
- Cost with paisa rounds half-up and the original is kept; zero cost stays unknown
- Cost above price, or a missing Tier C field, imports as provisional
- Add to stock is all-or-nothing and can be repeated for rows decided later
- Scanning onto a row attaches the barcode; a taken barcode is refused
- A changed selling price without the password is refused; other edits are not
- Undo deletes unused products and deactivates used ones
- Every import screen is Admin-only (403 for a cashier)
