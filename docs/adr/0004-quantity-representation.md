# 0004 — Quantity Representation

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)
Supersedes: the `quantity` shape proposed in ADR-0002

## Context

The shop sells two genuinely different kinds of goods:

- **Sealed pack goods** — tins, bottles, cartons, sacks handed over whole. A
  customer buys 4 packs of milk, never 4.25 of them.
- **Loose goods** — atta, sugar, rice, daal, loose tea, weighed out on a scale at
  the counter. A customer asks for derh kilo and gets 1.5 kg.

The clickable prototype shows only the first kind: every quantity in it is a whole
number with a plus/minus stepper. Taking that at face value would have produced an
integer `quantity` column that cannot express 1.5 kg at all.

This is frozen the moment the Phase 1 migration runs. Changing it afterwards means
re-interpreting the units of every historical row in `stock_movement`,
`sale_item`, and `product` on a database holding a real shop's trading history.

Confirmed with the client on 2026-09-08: **both kinds of goods are sold.**

## Decision

**All quantities are stored as integers counting thousandths of the product's
unit.** Column names carry a `_milli` suffix so the unit cannot be misread, exactly
as `_paisa` does for money.

| Real quantity | Stored value |
|---|---|
| 42 bags | `42000` |
| 4 packs | `4000` |
| 1.5 kg | `1500` |
| 750 g (0.75 kg) | `750` |
| 1 g | `1` |

Precision is therefore 1/1000 of a unit — one gram when the unit is a kilogram.
That is finer than any counter scale the shop will use.

`product` gains one column:

```sql
allows_fractional BOOLEAN NOT NULL DEFAULT 0
```

It controls **presentation and input only**, never storage. A sealed-pack product
(`allows_fractional = 0`) shows the plus/minus stepper from the prototype and its
quantity is always a whole multiple of 1000. A loose product
(`allows_fractional = 1`) accepts a typed decimal weight at the till.

The six affected columns become:

- `product.stock_quantity_milli`
- `product.low_stock_threshold_milli`
- `stock_movement.quantity_delta_milli` (signed)
- `stock_movement.quantity_before_milli`
- `stock_movement.quantity_after_milli`
- `sale_item.quantity_milli`

`product.sell_price_paisa` and `cost_price_paisa` are unchanged in meaning: they are
the price of **one whole unit** — one tin, or one kilogram. A line total is
therefore `quantity_milli * unit_price_paisa / 1000`, which does not divide evenly
in every case. The rounding rule for that division is a separate decision and is
being taken as its own question in this session; until it is settled, no line-total
code is written.

## Alternatives Considered

- **Plain integer units** — rejected. Cannot represent 1.5 kg, and the shop sells
  loose goods today, not hypothetically.
- **`FLOAT` or `REAL` quantity** — rejected outright. It reintroduces exactly the
  binary-rounding class of bug that Operating Rule 8 removes from money. A stock
  level that reads `2.9999999996 kg` after enough arithmetic is not acceptable in a
  ledger someone will audit.
- **`NUMERIC`/`DECIMAL`** — rejected. SQLite has no true decimal type; it stores
  such a column as text or float underneath, so the guarantee is illusory.
- **Two separate columns, one integer and one fractional** — rejected. Every query
  and every sum would have to handle both, and the invariant that they agree would
  have to be enforced by hand forever.
- **Hundredths (10 g precision) instead of thousandths** — rejected. It saves
  nothing real, and 10 g is coarse enough to be visibly wrong when weighing spices
  or saffron-priced goods.
- **A separate `unit_type` enum (`each` / `weight` / `volume`)** — deferred, not
  rejected. `unit_label` plus `allows_fractional` carries everything the till needs
  today. **Trigger for revisiting:** the first time a product must be bought in one
  unit and sold in another (a 50 kg sack broken down and sold by the kilo), which
  needs a real conversion factor and is a genuinely different feature.

## Consequences

**Easier:** one uniform quantity type everywhere, so no code branches on "is this
weighed or counted" to do arithmetic. Loose and packaged goods sum, deduct, and
reconcile identically. Integers throughout means stock maths is exact.

**Harder:** every raw database value is 1000× the human number, so anyone reading
the table directly must know the convention — which is why the `_milli` suffix is
mandatory rather than stylistic. Display and input both need a conversion at the
edge, and that conversion is a pure function with its own boundary tests.

**Forecloses:** nothing. Finer precision could be added later only by another
migration, but one gram is already below what a counter scale resolves.

## Consequential test cases (added to the edge-case matrix)

- A loose product sells 0.75 kg and stock drops by exactly 750 milli-units
- A sealed-pack product cannot be sold in a fractional quantity, rejected server-side
- Stock level displays as `1.5 kg` and `42 bags` from the same underlying column
- A quantity of 0 is rejected at the till for both product kinds
