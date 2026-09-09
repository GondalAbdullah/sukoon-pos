# 0011 — Catalog Onboarding

Status: **Accepted**
Date: 2026-09-09
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0008](0008-authentication-and-access-control.md), [ADR-0009](0009-multiple-barcodes-per-product.md)
Resolves: O-15, O-16

## Context

Neither governing document says how products get into the database the first time.
Phase 2 builds product CRUD and quietly assumes a populated catalog.

The prototype shows **1,248 items**. Entering those one at a time through a normal
product form — scan, name, cost, price, category, threshold, save — is on the order of
fifteen hours of standing at a terminal before the shop can ring up its first real
sale. That is a genuine risk to the project ever going live, and it was invisible in
both specifications.

Asked whether any existing digital record exists — a spreadsheet, an old system's
export, a supplier catalog — the client could not confirm one exists.

## Decision

### 1. A dedicated bulk-entry screen

One screen optimised for exactly one motion, repeated: **scan, type, Enter, next.**

- The scanner does the navigation. Scanning a code creates a new row and puts the
  cursor in the first field; Enter commits and returns focus to the scan field.
- Only the fields needed to sell the item: name, cost price, sell price, category,
  low-stock threshold. Everything else is edited later through the normal form.
- No page reloads — an htmx partial swap per committed row, per ADR-0001's rationale.
- Scanning a code that already exists jumps to that product rather than erroring, so
  a double-scan is a no-op instead of a duplicate.

### 2. Scan-as-you-go at the till

The catalog does not have to be complete before trading starts. When an unrecognised
barcode is scanned at the till, the sale is not blocked: the cashier is offered a
short inline form, the item is added, and the sale continues.

This matters more than the bulk screen does. It means the shop can open on day one
with a partly-filled catalog and let the busiest items arrive first, driven by what
customers actually buy.

### 3. Provisional products

An item added at the till is created as **provisional**: `product.is_provisional = 1`.

It has everything needed to complete the sale — barcode, name, selling price — and
nothing else. Cost price, category, and threshold are unset.

- Provisional products are listed in Stock under a "Needs completing" filter.
- Profit reporting excludes them from margin figures rather than reporting a false
  margin against a zero cost. An unknown cost is reported as unknown, never as zero.
- Completing one is an ordinary Admin edit, and clears the flag.

The flag is added now rather than later: adding a column to a live trading database
is a migration, and this one is a single boolean.

### 4. No CSV importer is built

**Trigger for revisiting:** the client produces an actual file — a spreadsheet, a
supplier list, an old system's export. At that point an importer is a few hours of
work against a real, known format. Written now, it would be written against an
imagined one.

## Which permission creates a product

ADR-0008 holds that anything setting a price is Admin-only, and creating a product
sets one. Read literally, a Cashier could not use scan-as-you-go at all, and every
unknown item would stall mid-queue.

That reading was rejected, and for a specific reason rather than convenience: the
strict rule does not hold in practice. On a busy evening it produces either a refused
sale with the goods in the customer's hand, or a shared Admin password. The second is
what actually happens, and it silently destroys every control in ADR-0008. A rule
that is routinely bypassed is worse than a narrower rule that is obeyed.

**Decision, confirmed by the client on 2026-09-09:** a Cashier may create a
**provisional** product, and only a provisional one.

They set a selling price, because they must in order to charge for it. The exception
covers exactly that one price and nothing else. A Cashier still may not edit an
existing product's price, create a price-override barcode, refund, or void — all
remain Admin-only and step-up protected.

What bounds the exception:

- the row is flagged `is_provisional` and can never be mistaken for a reviewed record
- `created_by_user_id` and a timestamp put a name on every one
- it appears under "Needs completing" in Stock, with a count on the stat card
- it is excluded from margin reporting, so an unknown cost never reports as profit

Deliberately **not** included:

- **No approval queue.** The item sells immediately; making the customer wait for the
  owner defeats the purpose.
- **No guessed cost price** — not a category average, not a percentage of the sell
  price. `NULL` means unknown and is reported as unknown.
- **No hard cap on the number of provisional products.** A cashier hitting a limit
  mid-queue is a blocked sale again. Visibility is the control, not a wall.

**Residual risk, stated plainly:** a dishonest cashier could create a provisional
product at a low price and pocket the difference. What limits it is attribution, a
visible review list showing the price they chose, and a count the owner sees whenever
he opens Stock. For a shop with a handful of staff and an owner usually present, that
is the proportionate control; a stricter one would be bypassed rather than obeyed.

## Alternatives Considered

- **A CSV importer as the primary path** — rejected. No file is known to exist, so the
  format would be invented. See the trigger above.
- **Requiring a complete catalog before go-live** — rejected. It puts fifteen hours of
  data entry between installation and any value, which is how a system gets abandoned
  before it is ever used.
- **Scan-as-you-go only, with no bulk screen** — rejected. It works, but it makes the
  first weeks of trading slower at the till, which is the worst place to put the cost.
- **Letting the till create fully-formed products** — rejected. It would put cost price
  and category in front of a cashier mid-queue, which is both slow and wrong: the
  cashier does not know the cost.
- **Blocking the sale on an unknown barcode** — rejected outright. The customer is
  standing there. A sale must never be blocked by a catalog gap.

## Consequences

**Easier:** the shop can start trading before the catalog is finished, and the catalog
completes itself in priority order. Bulk entry is available for a concerted push.

**Harder:** a provisional product is an incomplete record that must be visible and
chased, or it becomes permanent debt. The "Needs completing" filter is what stops that,
and it is a requirement rather than a nicety.

**Forecloses:** nothing. An importer can be added the day a file exists.

## Consequential test cases

- Bulk entry commits a row and returns focus to the scan field
- Scanning an existing code in bulk entry jumps to it rather than duplicating
- An unknown barcode at the till offers inline creation and the sale then completes
- A product created at the till is flagged provisional
- Provisional products appear in the "Needs completing" filter
- Margin reporting excludes provisional products rather than assuming zero cost
- Completing a provisional product clears the flag
- A Cashier cannot edit an existing product's price, only create a provisional one
