# 0005 — Weighed-Item Entry at the Till

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0004](0004-quantity-representation.md)

## Context

ADR-0004 established that loose goods are sold and quantities are stored in
thousandths. That immediately raised a question the Design System does not answer:
the prototype's cart row has only a whole-number plus/minus stepper, so there is no
designed way to put 1.5 kg of atta into a cart.

The client described the real counter workflow:

1. Packed goods are scanned as normal.
2. For an open item, the cashier reads the weight off a digital scale and types it;
   the price follows from the weight.
3. **Or the customer names an amount** — "I need Rs 200 worth of kidney beans" — the
   cashier types the amount, and the weight follows from it. This is a normal way to
   buy loose goods here, not an edge case.
4. A USB-connected scale or a label-printing scale may be added later. The design
   must accommodate that without a rewrite.

The scale is **not** connected to the PC today. There is no hardware integration to
build in v1.

## Decision

### Two entry directions, one resulting sale line

For any product with `allows_fractional = 1`, the till offers two ways to build the
line, and they produce an identical `sale_item`:

| Mode | Cashier types | System computes |
|---|---|---|
| **By weight** | `1.5` kg | line total from the unit price |
| **By amount** | `Rs 200` | the weight from the unit price |

Both are pure functions, in `services/pricing.py`, with no I/O:

```
compute_line_total_from_quantity(quantity_milli, unit_price_paisa) -> paisa
compute_quantity_from_amount(amount_paisa, unit_price_paisa)       -> quantity_milli
```

They are exact inverses only when the division comes out even, which it usually does
not. **The rounding rule that reconciles them is a separate decision, taken as its
own question in this session.** No line-total code is written until it is settled.

### The quantity's origin is recorded

`sale_item` gains one column:

```sql
quantity_source TEXT NOT NULL  -- 'stepper' | 'manual_weight' | 'manual_amount'
                               -- reserved: 'usb_scale' | 'scale_label'
```

Added now rather than later for two reasons. It is the audit trail for a disputed
line — "she asked for Rs 200 worth" is answerable a month later. And adding a column
to a live trading database is a migration, whereas including it now is free. The
two reserved values are deliberately unused in v1.

### Scanning becomes a resolver chain, not a lookup

Today the till resolves a scanned code with a single exact-match query on
`product.barcode`. That is a dead end for label-printing scales, whose barcodes
*encode* the weight or price inside the digits rather than identifying a product.

So the scan handler is written from the start as an ordered chain:

```
resolve_scanned_code(code) ->
    1. exact barcode match on product.barcode      # implemented in v1
    2. registered code parsers, in order            # empty in v1
    3. not found -> a calm "not recognised" result, never a crash
```

In v1 the parser list is empty and behaviour is identical to a plain lookup. Adding
support for a weighed-label barcode later means registering one parser — no change to
the till, the routes, or the schema.

### A scale is a source, not a special case

Quantity capture sits behind a single seam:

```
services/scales/
    base.py        # QuantitySource: read() -> quantity_milli | None
    manual.py      # ManualEntry — the only implementation in v1
```

A USB scale becomes a second implementation of the same interface. The till asks a
source for a quantity; it does not care whether a human or a serial port produced it.
`QuantitySource.read()` returning `None` is a first-class, honest outcome — a scale
that is unplugged or unread must degrade to manual entry, never block a sale.

### Deferred, with a concrete trigger

Hardware scale integration is **not built in v1**. It is not deferred to a vague
"later": the trigger is *the shop acquiring a scale and stating which model*, since
the barcode label format and the serial protocol are both manufacturer-specific and
usually configurable on the device itself. Guessing either now would be inventing
requirements.

## Alternatives Considered

- **Weight entry only, no amount entry** — rejected. "Rs 200 worth" is how customers
  actually buy loose goods here. Omitting it would push the cashier into doing
  division in their head at the counter, which is both slow and a source of disputes.
- **A separate "weighed sale" screen** — rejected. It splits one mental task across
  two places and contradicts the Design System's single-Till principle. The cart row
  itself changes shape per product instead.
- **Building the USB-scale integration now** — rejected as speculative. No scale
  exists to test against, and the protocol varies by model; code written against an
  imagined device is untested code that will need rewriting anyway.
- **A generic parser that guesses whether a barcode is weight-embedded** — rejected.
  Guessing at a barcode's meaning risks silently mis-pricing a sale. A parser is
  registered explicitly for a known format, or it does not run.
- **Storing only the amount and deriving weight at display time** — rejected. Stock
  deduction needs the weight as a first-class number; deriving it on every read would
  make stock levels depend on price history.

## Consequences

**Easier:** the cashier's real workflow is supported in both directions on day one,
with no hardware. Adding a scale later touches two new files and one registration,
not the till.

**Harder:** the cart row now has two shapes, and the Design System covers neither.
A designed component for fractional entry is now a Phase 3 requirement, and its
absence is on the open list.

**Forecloses:** nothing. Every reserved value and empty extension point is inert
until something registers against it.

## Consequential test cases

- Entering a weight produces the correct line total for a loose product
- Entering an amount produces the correct weight for a loose product
- The two modes agree with each other within the settled rounding rule
- `quantity_source` is recorded correctly for all three v1 entry paths
- An unrecognised scanned code returns a calm not-found result, not an exception
- A sealed-pack product offers no amount-entry mode
