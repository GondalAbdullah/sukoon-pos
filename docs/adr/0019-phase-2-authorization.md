# 0019 — Phase 2 Authorization for Catalog & Stock Management

Status: **Accepted** 2026-09-10 — direction confirmed by the client
Date: 2026-09-10
Phase: 2
Clarifies: [ADR-0008](0008-authentication-and-access-control.md) §4

## Context

ADR-0008 §4 listed "creating or deleting a product" and "performing stock-in and
stock-out" among actions *"not yet assigned and deferred to the Phase 3 gate, where
the specification already places them."*

That attribution is loose. The Development Specification places the **build** of
product/category CRUD and stock-in/out/adjustment squarely in **Phase 2**
(Section 11, Phase 2, steps 1 and 3), with no STOP AND ASK gate. The only Phase 3
gate is about discount rules and refund policy. Phase 2 cannot proceed while its
core deliverable has no one authorised to perform it.

## Decision

Confirmed with the client: **Admin-only for now; the finer taxonomy is refined at
the Phase 3 gate as ADR-0008 intended.**

### Two new permission codes, seeded to Admin only

| code | covers | admin | cashier |
|---|---|:-:|:-:|
| `catalog.manage` | create / edit / (soft- or hard-) delete a product; create / edit a category; assign or generate a plain barcode | ✓ | — |
| `stock.adjust` | record a stock-in, stock-out, or count correction | ✓ | — |

A Cashier has neither. The Cashier's one catalog capability — creating a
**provisional** product at the till (ADR-0011) — is a separate code
(`product.create_provisional`, already seeded) and is built in Phase 3 with the
till.

### What is *not* decided here, and still goes to the Phase 3 gate

- Whether `catalog.manage` / `stock.adjust` should be split finer (e.g. a separate
  `catalog.delete`), and whether any of them warrant **step-up** re-authentication
  the way `product.edit_price` and `sale.refund` do.
- Whether a future non-Admin "manager" role gets a subset.

These are exactly the open items ADR-0008 §4 parked; this ADR does not close them,
it just stops them blocking Phase 2.

### Already-Accepted rules that Phase 2 still honours as-is

- **Editing an existing product's *selling price*** stays `product.edit_price` —
  Admin-only **and step-up** (ADR-0008 §4/§5). `catalog.manage` covers every other
  product edit; a sell-price change additionally requires a step-up password.
- **Creating a price-override barcode** stays Admin-only and step-up (ADR-0009).
  It is gated in the route by a step-up check, not by a distinct permission code.

## Alternatives Considered

- **Let a Cashier manage the catalog** — rejected; contradicts ADR-0008's core
  split and the client's intent. Provisional-create is the deliberate narrow
  exception.
- **Pause for a full grill session** — considered; rejected by the client as
  disproportionate. The decision here is reversible (permission rows are data) and
  the genuinely hard questions are still going to the Phase 3 gate.
- **Reuse `product.edit_price` for all catalog management** — rejected; it would
  force a step-up password on routine edits like fixing a typo in a product name,
  which is friction that gets controls disabled (ADR-0008's own reasoning).

## Consequences

**Easier:** Phase 2 has a clear, minimal authorization story. Adding the finer
codes later is a seed change plus route-decorator edits.

**Harder:** the Phase 3 gate now has an explicit extra item — confirm or split
`catalog.manage` / `stock.adjust` and decide their step-up status. Recorded in
`context.md`.

**Forecloses:** nothing.

## Consequential test cases

- A Cashier hitting any `/stock` management route (create/edit/delete product,
  adjust stock, assign barcode) receives 403
- An Admin can create, edit, and delete a product and adjust stock
- Changing a product's **sell price** without a valid step-up password is refused,
  even for an Admin
- Creating a **price-override** barcode without a valid step-up password is refused
