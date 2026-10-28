# 0045 — Round the Bill Once, Not Each Line

Status: **Superseded** by [ADR-0046](0046-exact-amounts-and-store-style-receipt.md) (2026-10-29) — the client asked for the exact total, no Rounding line; §1 (lines exact to the paisa) and §3's refund cap carry over
Date: 2026-10-28
Phase: post-release (1.2.0)
Depends on: [ADR-0005](0005-weighed-item-entry.md), [ADR-0020](0020-phase-3-refund-and-discount-policy.md), [ADR-0034](0034-phase-6-reporting-policy.md)
Amends: [ADR-0007](0007-money-rounding.md) ("rounding happens exactly once, at the line"), [ADR-0044](0044-paisa-in-product-prices.md) §2–§3

## Context

ADR-0044 let product prices carry paisa and kept ADR-0007's rule: each line rounded to the rupee.
Trying it, the developer saw a Rs 150.50 item appear on the bill as Rs 151 and asked that the
till show **150.50 on the line, and the paisa in the bill's total too**.

Customers still pay in rupees: paisa coins are out of circulation. Offered three ways to settle
that (round the bill once; round only cash, leaving paisa in the Khata; no rounding at all), the
developer chose on 2026-10-28: **round the bill once, visibly**.

## Decision

### 1. Lines are exact to the paisa

A line's total is `unit price × quantity`, rounded half-up **to the paisa** (only a weighed
quantity can leave a fraction of a paisa). 3 × Rs 150.50 = **Rs 451.50**. A by-amount line (ADR-0005)
is still exactly the whole rupees the customer named.

The subtotal is the sum of the lines, paisa included.

### 2. The bill is rounded once, at the total, and says so

```
Subtotal                    Rs 561.50
Rounding                    +Rs 0.50
TOTAL                       Rs 562
```

`total = subtotal rounded half-up to the rupee`. The difference is shown as a **Rounding** line on
the till and on the receipt whenever it isn't zero. It is never stored separately: it is always
`total − subtotal` (there is no discount or tax, ADR-0020), so no migration.

Every payment method takes the rounded total. **Cash, change, card, the Khata entry, credit
limits, statements and WhatsApp messages stay whole rupees**; the invariant tests on
`sale.total_paisa`, payments and the ledger stay.

### 3. Refunds return whole rupees, and never more than was paid

Each refunded line is exact (as the sale line was); ADR-0044 §3's rule that a line's refunds can't
exceed it still holds, now at the paisa. The refund's **total** is rounded half-up to the rupee,
because it is paid back in cash or entered on the Khata, and is capped at what the sale has left:

- a refund that takes **everything still unrefunded on the sale** returns exactly what the
  customer paid minus earlier refunds (approved or pending);
- any other refund is its rounded total, capped at that remainder.

So a sale's refunds always sum to exactly its total.

### 4. Reports

Takings and payment-method totals use the sale total (what was paid). Category, product and
estimated-profit figures use line totals, now exact to the paisa, so they can differ from takings
by the rounding: at most 50 paisa per sale. ADR-0034 already calls profit an estimate.

### 5. The receipt shows the unit price

Each item line reads `3 x Rs 150.50` with its line total, so the customer can check the arithmetic.
This also closes a gap noted on 2026-10-23 (no unit price on the printed bill).

## Alternatives Considered

- **Round only cash; card and Khata exact** — rejected: puts paisa into Khata balances, credit
  limits, statements and WhatsApp messages: a ledger-wide change for 50 paisa.
- **No rounding** — rejected: change with paisa can't be handed over.
- **Keep rounding each line** (ADR-0044 as written) — what the developer asked to change.

## Consequences

**Easier:** the bill reads like the shelf: Rs 150.50 is Rs 150.50 until the very last line.

**Harder:** the lines add up to the subtotal, not the total; the Rounding line is what reconciles
them, so it must always be shown when non-zero.

## Consequential test cases

- 3 × Rs 150.50 → line Rs 451.50; subtotal and total with a Rounding line
- A weighed line is exact to the paisa
- Total, cash, change, payments and the Khata entry are whole rupees
- The receipt shows `qty x unit price`, Subtotal, Rounding (only when non-zero) and TOTAL
- Refunding everything returns exactly the total paid; piecewise refunds sum to it, never more
