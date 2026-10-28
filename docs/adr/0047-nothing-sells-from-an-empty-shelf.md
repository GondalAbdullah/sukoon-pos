# 0047 — Nothing Sells From an Empty Shelf; No Products Created at the Till

Status: **Accepted**
Date: 2026-10-29
Phase: post-release (1.2.0)
Supersedes: [ADR-0025](0025-stock-limits-at-the-till.md) §3–§4 (never-counted products uncapped, "found at the till"), [ADR-0011](0011-catalog-onboarding.md) §2–§3 (scan-as-you-go, provisional products created at the till)
Depends on: [ADR-0043](0043-product-spreadsheet-import.md)

## Context

Testing 1.2.0, the developer found two things at the till:

1. Typing **"shezan"** offered *"'shezan' isn't in the catalogue yet — add it?"* — though several
   Shezan products exist. The till resolved typed text only when it matched exactly one product;
   anything else fell through to the create-a-product form (ADR-0011 §2). He asked for the form
   to go.
2. A product with **0 in stock** could be added and sold. That was ADR-0025 §3, chosen by the
   client in September: a never-counted product's 0 meant "unknown", and the shortfall was booked
   as "found at the till". After the spreadsheet import (ADR-0043), *every* product is
   never-counted, so the rule made stock limits meaningless for the whole catalogue.

Offered three rules (block unless an Admin approves; block always; block counted, warn on
never-counted) with the consequence spelled out — after the import nothing sells until its stock
is entered — the developer chose on 2026-10-29: **block, always**.

## Decision

### 1. Every product is capped at its stock level

Counted or not, a product sells only what Sukoon has in stock: 0 means none. The till refuses to
add it ("Shezan Apple Jam is out of stock."), the + button and weigh box stop at the level, and
checkout's guarded stock update refuses the race the cart can't see. Nothing is booked as "found
at the till" any more; existing found-at-till movements stay in the history as they are.

### 2. The till never creates a product

- A scanned code or typed name matching **one** product adds it, as before.
- Typed text matching **several** products lists them (name, price, what's in stock) to pick from;
  out-of-stock ones are shown but can't be added. Up to 20 are listed; type more to narrow.
- Matching **nothing**: "Nothing in the catalogue matches '…'." New products are added by an
  Admin in Stock (Add product, Bulk entry, Import).

The `/till/new` route is gone. The `product.create_provisional` permission stays in the catalogue
(removing a seeded permission is a data change with nothing to gain) but nothing checks it.
Provisional products already in the catalogue keep their flag and stay under "Needs completing".

### 3. Stock is counted where barcodes are scanned

Because nothing sells until it has stock, the import's worklist gains an **In stock** box: typing
what's on the shelf records a count (a `correction` movement, "Counted on the import worklist",
`stock.adjust`). Scanning an item on and counting it are one motion. Stock can still be entered per
product in Stock as before.

## Consequences

**Harder:** after importing, the shop sells nothing it hasn't counted. A cashier who finds an item
"out of stock" that is on the shelf needs an Admin to enter its stock first.

**Easier:** stock levels mean what they say; low-stock and out-of-stock reports become trustworthy.

## Consequential test cases

- A never-counted product with 0 in stock can't be added, by id or by name; nothing is booked
- Checkout refuses a cart that needs more than is in stock, and the whole sale rolls back
- "shezan" lists the matching products; choosing an in-stock one adds it; an out-of-stock one is
  refused server-side
- An unknown code says nothing matches and offers nothing to create; `/till/new` is 404
- A count on the worklist records one correction movement and makes the product sellable
