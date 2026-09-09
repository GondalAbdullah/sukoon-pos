# 0012 — Product Field Requirements

Status: **Accepted**
Date: 2026-09-09
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0009](0009-multiple-barcodes-per-product.md), [ADR-0011](0011-catalog-onboarding.md)
Amends: the `product` table in ADR-0002

## Context

ADR-0011 introduced provisional products, and the first description of them was too
loose — "cost price is missing". The client pushed on it correctly: what if the name
is missing, or the SKU, or the barcode?

Those are not the same kind of gap, and treating them alike produces either a table
that rejects a legitimate product or one that accepts a useless row. Each field has
to be judged against one question: **can a cashier holding the item at the counter
honestly supply this?**

## Decision

Product fields fall into three tiers, and the tier decides nullability.

### Tier A — structurally required, `NOT NULL` always

**`name`**, **`sell_price_paisa`**.

A cashier can always supply both. The item is in their hand, so something can be
written down — "red chilli powder small packet" is a poor name but never an absent
one. And nothing can be sold without a price.

These may be **imprecise, never absent.** A weak name is fixed by an Admin during
review, not by permitting a blank. A nameless product cannot be searched, printed on
a receipt, or recognised a week later.

### Tier B — supplied by the system, never typed

`id`, `created_at`, `updated_at`, `created_by_user_id`, and the defaulted flags
`is_active` (1), `is_provisional`, `allows_fractional` (0), `stock_quantity_milli` (0).

### Tier C — genuinely unknowable at the counter, nullable, tracked by the flag

**`cost_price_paisa`**, **`category_id`**, **`low_stock_threshold_milli`**.

Cost price sits on a supplier invoice in the back office. Category is a judgement.
The threshold is a stocking decision, not a till decision. `is_provisional = 1` means
exactly "one or more Tier C fields are unfilled" — nothing more.

### `sku` — nullable, and the wider question is deferred

`sku TEXT NULL UNIQUE`.

A SKU is the shop's own internal code. It is not printed on the product, so it never
"fails to appear" — it was never there. ADR-0002 had it `NOT NULL UNIQUE`, which
would have required somebody to invent a unique code for every one of roughly 1,248
products, and a cashier to conjure one mid-queue. That was an impossible requirement
and it survived undetected until the client questioned it.

SQLite's UNIQUE constraint permits multiple NULL values, so a nullable unique column
gives precisely the wanted behaviour: many products with no SKU, and no duplicates
among those that have one.

**Deferred:** whether the shop keeps SKUs at all, and in what format if so.
**Trigger:** the client confirming whether Mr. Abdullah writes his own codes on shelf
labels, supplier orders, or stock-taking sheets. If he does, the generated format
should match what he already writes. If he does not, the column can be dropped or
left permanently empty. Tracked as O-17.

### Barcode absence is normal, not incomplete

A product has zero or more barcodes (ADR-0009). **Zero is a complete, correct
product** — loose atta, unbranded goods, a local bakery item. Nothing to scan, ever;
it is found by name search.

A barcode-less product is explicitly **not** provisional and must never appear in
"Needs completing". Nagging forever about a label that will never exist would train
the owner to ignore the list, which is the one thing that makes provisional products
safe.

Two situations hide under "the barcode doesn't appear", and only one is a gap:

| Situation | State |
|---|---|
| Item has a barcode, catalog does not know it | Scan-as-you-go; the barcode **is** known |
| Item has no barcode at all | Normal, complete product; found by name |

## Alternatives Considered

- **All fields nullable, validity enforced in application code** — rejected. The
  database is where an invariant survives a bug in a route handler.
- **All fields required, no provisional state** — rejected. It blocks a sale with the
  customer present, which ADR-0011 already ruled unacceptable.
- **Defaulting cost price to zero rather than NULL** — rejected outright. It reports a
  fake 100% margin and silently corrupts the shop's total profit figure. An unknown
  cost is reported as unknown.
- **Auto-generating a placeholder name** ("Unknown item 1249") — rejected. It defers
  the one piece of information only the person holding the item can supply, and does
  it at the exact moment supplying it is easiest.
- **Treating a missing barcode as provisional** — rejected, as above.
- **Keeping `sku NOT NULL` and auto-generating it now** — rejected only because the
  client chose to defer the question. Auto-generation remains the recommendation if
  SKUs are kept.

## Consequences

**Easier:** the table accepts every legitimate product, including barcode-less loose
goods and half-known till creations, while still refusing a row that cannot be sold
or found. The "Needs completing" list contains only genuine work.

**Harder:** three tiers is more nuance than "required or optional", and anyone adding
a field later must decide which tier it belongs to rather than defaulting to nullable.

**Forecloses:** nothing. Tightening `sku` later is a migration, which is exactly why
it is nullable now rather than guessed at.

## Consequential test cases

- A product cannot be created with a null or empty name
- A product cannot be created with a null selling price
- A product with a null cost price is accepted and flagged provisional
- A product with no barcode is accepted and is **not** flagged provisional
- Two products may both have a null SKU; two may not share a non-null SKU
- Margin reporting reports unknown-cost products as unknown, never as zero cost
