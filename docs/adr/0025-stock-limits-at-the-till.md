# 0025 — Stock Limits at the Till

Status: **Accepted** 2026-09-14 — chosen by the client
Date: 2026-09-14
Phase: 3 (addendum, after functional sign-off)
Resolves: **O-22**
Depends on: [ADR-0004](0004-quantity-representation.md), [ADR-0005](0005-weighed-item-entry.md), [ADR-0011](0011-catalog-onboarding.md) §2 (scan-as-you-go), [ADR-0012](0012-product-field-requirements.md)
Fixes: a latent bug in ADR-0011 §2's flow (see Context)

## Context

The cart accepted any quantity of anything. Stock was checked only inside
`record_sale`, whose guarded update refuses to take a level below zero — so the books
were always safe, but the cashier found out at checkout, after the customer had
queued, from a message that didn't say which product ("Only 0 bottle in stock.").

The client's rule: **warn earlier.** When an item is in limited supply, the + button
stops working the moment the cart holds all of it.

Checking how that rule would treat an item created mid-sale (ADR-0011 §2) exposed a
bug that already existed: such a product is created with zero stock, so **checkout
always refused it**. Verified in session 21 by a throwaway test — create "Local
Biscuits" at the till, check out, get "Only 0 unit in stock." No test had ever sold
one. Scan-as-you-go has never worked end to end.

A second finding shaped the rule. The obvious marker for "created at the till" —
`product.is_provisional` — does not mean that. Per ADR-0012 it means *any* Tier C
field is empty (cost, category, low-stock threshold), which covers most bulk-entered
products indefinitely, since a threshold is optional. Exempting provisional products
would have exempted much of the catalogue and hollowed out the client's rule.

## Decision

**A product's quantity is capped at the till only once Sukoon has been told how many
exist.**

1. **Counted vs never counted.** A product is *counted* once it has at least one
   `stock_in` or `correction` movement that a person recorded. Until then it is
   *never counted*: Sukoon has no idea how many are on the shelf, so a zero level
   means "unknown", not "none". This is derived from the movement history — no new
   column, no migration.
2. **Counted products are capped at their stock level**, summed across every cart
   row for that product:
   - Sealed packs: the **+** button is disabled when the cart holds the whole level,
     with a short amber caption saying so (Design System §13: state is never colour
     or a dead control alone). Scanning it again at the limit is refused by name.
   - A counted product at zero cannot be added: "*Cooking Oil 1L* is out of stock."
   - Loose goods: a weight or amount that would take the cart past the level is
     refused, naming what's left ("Only 1.5 kg of *Atta (loose)* left to sell").
   - Every limit is enforced **server-side** on add / + / set-weight / set-amount.
     The disabled button is the courtesy, not the control.
3. **Never-counted products are not capped** (the client's choice). At checkout,
   inside the same all-or-nothing sale transaction, Sukoon first records a
   `stock_in` for exactly the shortfall, with reason "Found at the till — not yet
   counted (INV-…)" and `reference_type = "found_at_till"`, then records the sale.
   The level ends at a truthful zero and the history shows who sold it and when.
4. **"Found at the till" movements never make a product counted.** Otherwise the
   first sale would cap every later one at zero. Only a person's delivery or count
   does.
5. **Checkout's own refusal stays**, for the race the cart cannot see — another till
   selling the last one between add and checkout — and now names the product.

## Alternatives Considered

- **Exempt `is_provisional` products.** Lost: wrong meaning (see Context).
- **Record the origin ("created at the till") in a new column.** Precise for the
  till-created case, but misses its twin: a bulk-entered product nobody has stocked
  in yet is in exactly the same state — in the customer's hand, never counted. It
  also needs a migration against ADR-0016's frozen schema for a fact the movement
  history already holds.
- **Ask "how many?" when creating an item at the till** (offered to the client).
  Lost: an extra field at the busiest moment, and it still wouldn't help the
  bulk-entered twin.
- **Cap never-counted products at zero too** (offered to the client). Lost: nothing
  created or bulk-entered could be sold until an Admin booked stock in, which
  defeats ADR-0011's fast go-live.
- **Allow negative stock for uncounted products.** Rejected: breaks the non-negative
  guard the concurrency tests rely on, and "−3 bottles" is not a truth anyone can
  act on.

## Consequences

- **Easier:** a cashier can't build a cart the shop can't fill; the rare race is
  reported by name. Scan-as-you-go works for the first time. Day-one onboarding
  (bulk entry, no stock-ins yet) can sell immediately.
- **Harder:** the till reads each cart product's counted state and level on every
  render (one query for the whole cart, not one per row).
- **Honest cost:** a never-counted product can be sold in any quantity, so a
  dishonest or careless cashier could ring a bigger quantity than exists — the
  same trust boundary ADR-0011 already accepted for till-created products. The
  audit trail names the user on every "found" movement.
- **Follow-up, not done here:** the Stock screen still shows a never-counted
  product at 0 as coral "out of stock". Semantically that item is "not counted".
  Worth a small visual distinction later; recorded in context.md §4.

### Consequential test cases
- Sealed, counted, level 2: add, +, then + again is refused; the rendered + is disabled with a caption.
- Counted at zero: scanning is refused by name.
- Loose, counted, 2 kg: 2.5 kg is refused; 1.5 kg on one line then 1 kg on a second is refused.
- Never counted: + is never capped; checkout books a found stock_in of the shortfall, then the sale; level ends at 0.
- A second sale of the same never-counted product still succeeds (found movements don't count).
- A product created at the till sells end to end (the latent ADR-0011 §2 bug).
- Checkout's refusal for a race names the product.
