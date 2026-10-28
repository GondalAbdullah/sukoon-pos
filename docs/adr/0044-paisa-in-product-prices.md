# 0044 — Paisa in Product Prices

Status: **Accepted**
Amended by: [ADR-0045](0045-round-the-bill-not-the-line.md) (2026-10-28) — §2/§3: the till shows lines with paisa; the rounding moves from each line to the bill's total, and a refund's total is rounded and capped per sale
Amended by: [ADR-0046](0046-exact-amounts-and-store-style-receipt.md) (2026-10-29) — the bill is exact too; nothing is rounded to the rupee
Date: 2026-10-28
Phase: post-release (1.2.0)
Depends on: [ADR-0004](0004-quantity-representation.md), [ADR-0005](0005-weighed-item-entry.md), [ADR-0020](0020-phase-3-refund-and-discount-policy.md), [ADR-0043](0043-product-spreadsheet-import.md)
Amends: [ADR-0007](0007-money-rounding.md) (the invariant "every persisted money value is a whole number of rupees"), [ADR-0043](0043-product-spreadsheet-import.md) §3 (costs rounded to the rupee)

## Context

ADR-0007 made the rupee the only unit: every stored money value a multiple of 100 paisa,
validated on product create and edit. The developer chose that deliberately.

The shop's own data says otherwise. The client's product export has **2,955 cost prices with
paisa** (`4.30`, `1594.23`) — the old system kept average costs. ADR-0043 rounded them to the
rupee to fit ADR-0007, which for a Rs 5 item is a 7% error in its cost. The developer decided on
2026-10-28: **if paisa is being used, Sukoon should keep it, not round it away** — for cost
prices and selling prices both.

What has not changed: paisa coins are out of circulation, and a customer pays in rupees.

## Decision

### 1. Product prices may carry paisa

`product.cost_price_paisa`, `product.sell_price_paisa` and `product_barcode.price_override_paisa`
take any non-negative whole number of paisa: Rs 105.50 is `10550`. Storage was already paisa
(ADR-0007 kept the finer unit "so a future price with paisa in it would not require a
migration") — **no migration**. Input accepts at most two decimals; a third is refused, not
rounded, so what the owner typed is what is stored.

The importer keeps the file's paisa exactly (ADR-0043 §3 amended). A figure with more than two
decimals in a file (`1594.233`) is rounded half-up to the paisa; that is the only rounding left
in the import.

### 2. What is charged stays whole rupees — rounded once, at the line

ADR-0007's rule already covers this, because it was written for weighed goods: a line's total is
`unit price × quantity`, rounded **half-up to the rupee in one step**. A Rs 105.50 item:

```
1 × Rs 105.50  = Rs 105.50 → Rs 106
3 × Rs 105.50  = Rs 316.50 → Rs 317   (not 3 × Rs 106 = Rs 318)
```

Sale line totals, subtotal, discount, total, tendered, change, Khata entries, statements and
WhatsApp messages stay whole rupees, and their invariant stays tested. The by-amount entry
(ADR-0005) stays whole rupees: the customer names a rupee amount.

### 3. A line's refunds never add up to more than it was charged

Refunding part of a line computes `refunded quantity × unit price` rounded to the rupee. Done in
pieces, that can exceed the line: three Rs 105.50 items charged Rs 317 refund at Rs 106 each,
Rs 318. (The same was already possible with weighed goods; paisa prices make it ordinary.) Now:

- a refund that covers **the rest of a line** returns exactly the money left on it
  (line total − what earlier refunds, approved or pending, already returned);
- any other partial refund is the rounded figure, capped at the money left on the line.

So the refunds of a line always sum to its charged total, exactly.

### 4. Display

A price shows paisa only when it has some: `Rs 105.50`, but `Rs 1,050` as before. Totals and
balances, which are whole rupees, look exactly as they did.

### 5. Estimated profit and stock value

They use the exact cost. Each line's cost (`cost × quantity`) is still rounded to the rupee as
ADR-0034 already does, so reports stay in rupees.

## Alternatives Considered

- **Cost prices only** — offered as the smaller change; the developer chose both.
- **Paisa everywhere, including payments and Khata** — rejected: customers cannot pay it, and
  it would reverse ADR-0007's line rounding that receipts and the Khata depend on.
- **Rounding each item to the rupee before multiplying** (3 × Rs 106) — rejected: it charges
  more than the shelf price says, and differs from how weighed goods already work.

## Consequences

**Easier:** cost and price are what the supplier and the shelf say, to the paisa; profit
estimates on cheap items stop being off by several percent.

**Harder:** a single item's charge (Rs 106) differs from its shelf price (Rs 105.50); the receipt
and till show both. The owner should know that a Rs x.50 price rounds up for one item.

## Consequential test cases

- A product saves with Rs 105.50 for cost and price; a third decimal is refused
- One item at Rs 105.50 charges Rs 106; three charge Rs 317
- Every sale line total, subtotal and total is still a whole rupee
- Three one-item refunds of that line return Rs 317 in all, never Rs 318
- The importer keeps `4.30` as Rs 4.30
- Prices display with paisa only when there is some
