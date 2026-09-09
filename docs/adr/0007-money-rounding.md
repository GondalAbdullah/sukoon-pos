# 0007 — Money Rounding and the Rupee Boundary

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0004](0004-quantity-representation.md), [ADR-0005](0005-weighed-item-entry.md)

## Context

Paisa coins are out of circulation. Every price in this shop is a whole number of
rupees, and customers pay whole rupees.

But loose goods manufacture sub-rupee amounts out of whole-rupee prices. Kidney beans
at Rs 480/kg, a customer asking for Rs 200 worth:

```
weight = 20000 paisa x 1000 / 48000 = 416.666... milli-units
```

Rounded to 417 milli and recomputed, the line total is Rs 200.16. Rounded to 416, it
is Rs 199.68. The customer asked for a round number and arithmetic cannot give them
one. Something has to give, and the choice must be recorded, because a future reader
who finds `line_total != quantity x price` on a line will otherwise "fix" it into
something wrong.

Confirmed with the client on 2026-09-08: prices are whole rupees, paisa are not
transacted, and customers ask for round amounts (Rs 50, Rs 70, Rs 100), not
Rs 456.

## Decision

### Storage stays in paisa; the rupee is a business rule

Money remains an integer count of paisa in every column, per Operating Rule 8 and
ADR-0002. Paisa is the *storage* unit; the rupee is the *transaction* unit. Keeping
the finer unit costs nothing, gives headroom for intermediate arithmetic, and means
a future price with paisa in it would not require a migration.

**Invariant:** every persisted money value is a whole number of rupees, i.e. a
multiple of 100 paisa. This is asserted in tests, not merely intended.

### Rounding happens exactly once, at the line

```
unit price          whole rupees, validated on product create/edit
line total          computed, then rounded half-up to the nearest rupee
cart subtotal       the sum of already-rounded line totals
discount            whole rupees
total               subtotal - discount (+ tax, pending O-3)
change              whole rupees, trivially
Khata ledger        whole rupees throughout
```

Rounding at the **line** and then summing is deliberate, and it is the opposite of
the common mistake. If lines were left unrounded and only the grand total rounded,
the printed lines would not add up to the printed total — and a customer checking a
receipt by hand would find the shop's own paper disagreeing with itself. Summing
already-rounded lines cannot produce that.

Half-up, not banker's rounding: Rs 159.50 becomes Rs 160. It is what a person at a
counter expects, and the fairness argument for banker's rounding does not apply at
this volume.

The rounding helper takes and returns integer paisa and handles sign explicitly
(away from zero), so that a refund mirrors its sale exactly:

```
round_paisa_to_rupee(paisa: int) -> int   # pure, exhaustively boundary-tested
```

### For amount entry, the typed amount is authoritative

When the cashier types "Rs 200 worth of kidney beans":

- `line_total_paisa` = **exactly the amount typed**. It is not recomputed.
- `quantity_milli` = derived from it and rounded to the nearest milli-unit.
- `quantity_source` = `manual_amount`.

The customer asked for Rs 200 and pays Rs 200. The weight is what the scale
approximately showed; the money is exact. This is what actually happens at a counter,
and inverting it — charging Rs 200.16 because the arithmetic said so — would be the
software correcting the shop about its own transaction.

**Consequence, stated plainly so nobody later calls it a bug:** on amount-entry lines
`line_total_paisa != round(quantity_milli x unit_price_paisa / 1000)`, by up to half
a rupee. `quantity_source` is what makes that discrepancy explainable rather than
mysterious. Every other line kind satisfies the identity exactly.

A typed amount must itself be a whole rupee; a fractional amount is rejected at input.

### Refunds reverse recorded amounts, never recompute

A refund returns the `line_total_paisa` that was actually stored on the original
line. It does not recompute from quantity and price, because the price may have
changed since, and because on an amount-entry line the recomputation would not match
what the customer paid.

## Alternatives Considered

- **Store whole rupees instead of paisa** — rejected, though genuinely tempting given
  that nothing sub-rupee is ever transacted. Paisa costs nothing, matches Operating
  Rule 8's own example, and leaves room for an intermediate value or a future
  paisa-denominated price without a migration against live data.
- **Trust the weight and charge Rs 200.16** — rejected. It preserves a tidy
  arithmetic identity at the cost of handing the customer a number they did not ask
  for and cannot pay in coins.
- **Round the grand total only, leaving lines unrounded** — rejected. Produces a
  receipt whose lines do not sum to its own total.
- **Round to the nearest Rs 5** — rejected. The client did not ask for it, prices are
  already whole rupees, and it would silently overcharge on small items.
- **Banker's rounding (half-to-even)** — rejected. Surprising at a counter, and its
  statistical fairness benefit is irrelevant at single-shop volume.
- **Floating point anywhere in the chain** — rejected outright, per Operating Rule 8.
  `Decimal` is likewise avoided in storage since SQLite has no true decimal type.

## Consequences

**Easier:** every printed number is a whole rupee, every receipt's lines sum to its
own total, and change is always payable in real currency. The rounding logic is one
pure function that can be tested exhaustively at its boundaries.

**Harder:** one deliberate, documented exception to the "line total equals quantity
times price" identity exists, on amount-entry lines only. Anyone auditing the data
must know it is intentional — which is why it is written here and in the glossary.

**Forecloses:** nothing. Rs 5 rounding or paisa-denominated pricing could be layered
on later, since the storage unit is finer than the transaction unit.

## Consequential test cases

- `round_paisa_to_rupee` is correct at boundaries: 0, 1, 49, 50, 51, 99, 100, 149, 150
- The same function is symmetric for negative values (refunds mirror sales exactly)
- A receipt's printed line totals always sum exactly to its printed subtotal
- Every persisted money column holds a multiple of 100 paisa
- A typed amount that is not a whole rupee is rejected at input
- An amount-entry line stores exactly the amount typed, not a recomputed value
- A refund of an amount-entry line returns exactly what the customer paid
