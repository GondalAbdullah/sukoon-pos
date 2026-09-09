# 0009 — Multiple Barcodes Per Product, With Price Override

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0008](0008-authentication-and-access-control.md)
Supersedes: the single `product.barcode` column proposed in ADR-0002

## Context

ADR-0008 records that no discount mechanism is built. A reduced price is instead
applied by relabelling goods with a new barcode at the lower price.

Confirmed with the client on 2026-09-08: this applies to a **subset of physical
units** — near-expiry stock, damaged packaging, a clearance batch — while the rest of
the same product continues to sell at full price. A permanent change to the actual
retail price is a different thing entirely: that is editing the product's price,
which ADR-0008 already makes Admin-only.

That distinction is what forces a data model decision. Twenty cans of Dalda 5L, five
of them relabelled, must remain **one stock number of twenty**.

## Decision

A product has many barcodes. Each may carry its own price.

```sql
product_barcode (
  id                   INTEGER PK,
  product_id           INTEGER FK -> product.id,
  barcode              TEXT NOT NULL UNIQUE,   -- unique across the whole catalog
  price_override_paisa INTEGER NULL,           -- NULL = use product.sell_price_paisa
  label                TEXT NULL,              -- "Near expiry, Oct", for the humans
  is_active            BOOLEAN NOT NULL DEFAULT 1,
  created_by_user_id   INTEGER FK -> user.id,
  created_at           DATETIME NOT NULL
)
```

`product.barcode` is removed. The manufacturer's own barcode becomes simply the first
row in this table, with a `NULL` override.

**Resolution order when a code is scanned**, extending the chain from ADR-0005:

```
1. product_barcode where barcode = code and is_active = 1
      -> product, and price = price_override_paisa or product.sell_price_paisa
2. registered code parsers                        # empty in v1
3. not found -> a calm "not recognised" result
```

Stock is untouched by any of this. Both barcodes point at the same `product_id`, so
selling a relabelled can moves the single stock number from 20 to 19. There is no
reconciliation, no merge when a promo ends, and the low-stock alert keeps working on
one number.

`sale_item` gains `product_barcode_id` (nullable, FK). The line already snapshots the
price charged; this records *which label* produced it, so "why was this cheaper" is
answerable a month later rather than inferred.

Ending a promotion is setting `is_active = 0`. The row is never deleted — historical
sale lines reference it.

**Creating a price-override barcode is a destructive action** under ADR-0008: it is
Admin-only and step-up protected. It sets a price, and anything that sets a price
gets the same protection as editing one.

## Alternatives Considered

- **A second product record for the relabelled units** — rejected. It splits the one
  number the entire inventory system exists to keep correct. "How much Dalda do I
  have?" would become a sum across records that low-stock alerting treats as
  unrelated, reports would list the product twice, and a dead record would be left
  behind when the batch sold out.
- **A `discount` table keyed to products with date ranges** — rejected. That is the
  discount engine ADR-0008 deliberately declined to build, arriving through a side
  door. It also cannot express "these five cans, not those fifteen."
- **A free-form price field the cashier types at the till** — rejected. No audit
  trail, no Admin gate, and it makes every sale a negotiation.
- **Keeping `product.barcode` and adding an override table beside it** — rejected.
  Two places to look up a barcode is two places to get wrong, and uniqueness would
  have to be enforced across both.
- **Physical-unit tracking (a row per can)** — rejected as far beyond scope for a
  general store, and it would not survive contact with loose goods at all.

## Consequences

**Easier:** one stock number per product, always. Relabelling is additive and
reversible. The same table absorbs a product that legitimately carries two
manufacturer barcodes — a repackaged size, an old and new label — which the single
column could not represent at all.

**Harder:** one more join on the hottest path in the system, the till scan. It is an
indexed unique lookup, so the cost is negligible, but the query is no longer trivial.

**Forecloses:** nothing. A future date-ranged promotion could hang off this table.

## Open, and deliberately not decided here

How the physical label gets produced — a dedicated barcode label printer, adhesive
sheets from an ordinary printer, or the existing thermal receipt printer — is a
hardware and cost question for the client, tracked as **O-14**. It changes what
Phase 2 builds, but nothing in this schema.

## Consequential test cases

- Two barcodes on one product both resolve to it, at their respective prices
- Selling via an override barcode deducts stock from the single shared count
- A barcode is unique across the entire catalog, enforced at the database level
- Deactivating a barcode stops it resolving, without affecting historical sale lines
- A product's normal price is unaffected by an override barcode existing
- Creating an override barcode without step-up authentication is refused
- `sale_item.product_barcode_id` records which label produced the price
