# 0020 — Phase 3 Refund & Discount Policy

Status: **Accepted** 2026-09-11 — direction confirmed by the client at the Phase 3 STOP AND ASK gate
Date: 2026-09-11
Phase: 3 (POS & Billing)
Closes: the Phase 3 STOP AND ASK gate (Development Specification, Section 11, Phase 3)
Refines: [ADR-0008](0008-authentication-and-access-control.md) §4 (refund authority)
Closes the open item in: [ADR-0019](0019-phase-2-authorization.md) ("What is *not* decided here")
Resolves: **O-7** (refund flow had no design)

## Context

The Development Specification places a 🛑 STOP AND ASK gate at the close of
Phase 3:

> Confirm discount rules (max discount %, who can apply it) and refund policy before
> this logic is locked in — both directly affect the ledger and stock correctness.

ADR-0019 additionally parked one item for this gate: whether `catalog.manage` /
`stock.adjust` should be split finer or gain step-up.

The gate cannot be passed by an agent alone (CLAUDE.md, non-negotiable rules). The
client was asked the four questions below on 2026-09-11 and answered them; this ADR
records the answers and the design that follows from them.

## Decision

### 1. Discounts — none, confirmed

ADR-0008 §6 already decided that v1 builds **no discount mechanism**. The client
confirmed this still holds as Phase 3 builds the till.

- The till has no discount control of any kind.
- `sale.discount_paisa` and `sale_item.line_discount_paisa` stay in the schema
  **fixed at zero**. No UI, service function, or route may set them non-zero.
- A required test asserts that no code path in the sale flow can persist a non-zero
  discount (context.md §5, "No code path anywhere can set a non-zero discount in v1").
- A reduced price is still handled only by relabelling goods with a price-override
  barcode (ADR-0009), which is Admin-only and step-up.

Nothing new is built for this item; it is a confirmation that the existing
constraint carries into Phase 3.

### 2. Refund authority — Cashier initiates, Admin approves

This **refines ADR-0008 §4**, which said a refund is "Admin only". It is not a
silent override (CLAUDE.md): the change is that a Cashier may now *start* a refund,
but a refund still cannot *complete* without an Admin.

| Step | Who | Auth |
|---|---|---|
| Initiate a refund against an existing sale | Cashier or Admin | permission `sale.refund_initiate` |
| Approve (authorise) a pending refund | **Admin only** | permission `sale.refund` **+ step-up** |
| Reject a pending refund | Admin only | permission `sale.refund` |

- A Cashier initiating a refund creates a `refund` row in status
  `pending_approval`. **No stock moves, no ledger entry, no cash leaves the drawer**
  until an Admin approves.
- The approving Admin re-enters their password (`sale.refund` stays in
  `STEP_UP_PERMISSIONS`). Step-up authorises exactly that one approval.
- There is **no** unattended-Cashier refund path and **no** value cap that lets a
  Cashier self-authorise. Every refund is Admin-approved. (The "Cashier can refund
  within limits" option was offered and not chosen.)
- The `refund` row records `initiated_by_user_id` and `approved_by_user_id`
  distinctly, so a refund always names both the Cashier who rang it and the Admin
  who authorised it — the same shape as the credit-limit override in ADR-0014.

### 3. Refund mechanics — all four rules enforced

The client selected every rule offered.

**a. The original invoice is required.**
A refund references an existing `sale` by id. There is no receiptless / blind
refund. A line may be refunded only up to `quantity_sold − quantity_already_refunded`
for that `sale_item`; the service rejects an over-refund before anything is written.

**b. Partial refunds are allowed.**
A refund may cover selected lines and a partial quantity of a line, not only the
whole invoice.

- On `stepper` and `manual_weight` lines, a partial quantity refunds
  `round_paisa_to_rupee(unit_price_paisa_snapshot × refunded_milli / 1000)`
  (ADR-0007 half-up, at the line).
- On `manual_amount` lines (ADR-0007: the typed money is authoritative, and
  `line_total ≠ quantity × price` by design), **partial-quantity refunds are not
  offered**. Such a line is refunded whole or not at all, and a whole-line refund
  returns exactly `line_total_paisa` — "exactly what the customer paid"
  (context.md §5).

**c. Refunded goods are restocked automatically.**
Approving a refund posts, in the same transaction, a `stock_movement` of
`movement_type = 'refund'` that **increases** the product's stock by the refunded
milli-quantity, with the refund's reason copied onto the movement.

- *Deliberate addition beyond the literal answer, flagged for the client:* each
  `refund_item` carries a `restock` boolean, default **true**. An Admin may untick
  it at approval for a line that came back damaged; that line then posts no stock
  movement. This is a real general-store need (a returned leaking bottle does not go
  back on the shelf) and costs one column and one checkbox. If the client prefers
  "always restock, no exceptions", drop the column — the default already gives that
  behaviour.

**d. Credit-sale refunds reverse the ledger.**
If the original `sale.payment_method == 'credit'`, approving the refund posts a
`credit_ledger_entry` of `entry_type = 'refund'` with a **negative** `amount_paisa`,
reducing the customer's balance, and updates `customer.balance_paisa`. **No cash
leaves the drawer** for a credit refund.

For a `cash` or `card` original sale, the refund is paid out as cash
(`refund.method = 'cash'`) — v1 has no card-processor integration, so a card sale
is refunded from the drawer, and the receipt says so. `refund.method = 'card'` is a
reserved value for a later phase.

Per ADR-0015, a refund entry **does not** reset the customer's overdue clock — only
a genuine `payment` does. That rule is already Accepted and is unchanged here.

### 4. `catalog.manage` / `stock.adjust` — stay coarse, Admin-only, no step-up

The client chose "keep as-is". This **closes** the ADR-0019 open item.

- `catalog.manage` remains one permission covering create / edit / soft- or
  hard-delete of a product, create / edit of a category, and assigning or
  generating a plain barcode. Admin-only. **No step-up.**
- `stock.adjust` remains one permission covering stock-in, stock-out, and count
  correction. Admin-only. **No step-up.**
- The two carve-outs already in force are unchanged: a **sell-price change**
  (`product.edit_price`) and a **price-override barcode** are Admin-only **and**
  step-up.
- A finer split (`catalog.delete`, a `manager` role subset) is **declined for v1**.
  Revisit trigger: a third role is introduced, at which point the split is a seed
  change plus route-decorator edits.

## Data model — new `refund` and `refund_item` tables

ADR-0016's schema has no place to record a refund transaction: `sale.status` has
`'refunded'` / `'partially_refunded'` values and `stock_movement` /
`credit_ledger_entry` both have a `'refund'` type, but nothing captures *which* sale,
*which* lines, *how much*, *who initiated*, *who approved*, and the pending state
before approval.

Per ADR-0016's own rule ("any change is a new migration, never an edit to
`…_phase_1_initial_schema…`"), Phase 3 adds a **new migration** with two tables:

```
refund
  id                     INTEGER PK
  sale_id                INTEGER FK -> sale.id   NOT NULL      -- the original invoice (rule a)
  total_paisa            INTEGER NOT NULL                       -- positive; sum of refund_item line totals
  method                 TEXT NOT NULL     -- 'cash' | 'credit_ledger'   ('card' reserved)
  reason                 TEXT NOT NULL     -- mandatory, non-blank (CHECK), like a stock movement
  status                 TEXT NOT NULL     -- 'pending_approval' | 'approved' | 'rejected'
  initiated_by_user_id   INTEGER FK -> user.id   NOT NULL
  approved_by_user_id    INTEGER FK -> user.id   NULL          -- the Admin; set on approve/reject
  created_at             DATETIME NOT NULL
  resolved_at            DATETIME NULL                          -- approved or rejected at

refund_item
  id                     INTEGER PK
  refund_id              INTEGER FK -> refund.id   NOT NULL
  sale_item_id           INTEGER FK -> sale_item.id   NOT NULL
  quantity_milli         INTEGER NOT NULL      -- <= sold - already-refunded for that sale_item (CHECK > 0)
  line_total_paisa       INTEGER NOT NULL      -- amount refunded for this line (whole rupees)
  restock                BOOLEAN NOT NULL DEFAULT 1   -- rule c; unticked = damaged, no stock movement
```

- **Stock and ledger effects fire only on approval**, all inside one transaction
  with the `refund.status` change to `'approved'` and the parent `sale.status`
  transition. A crash mid-approval leaves the refund `pending_approval` and no
  partial state (context.md §5, atomicity).
- `sale.status`: `'completed'` → `'partially_refunded'` while some refundable
  quantity remains → `'refunded'` once every line is fully refunded.
- Money invariant (ADR-0007): every `line_total_paisa` and `total_paisa` is a whole
  number of rupees. A refund of a line mirrors its sale under
  `round_paisa_to_rupee`'s explicit-sign behaviour.
- No human-facing "refund number" in v1 — a refund is identified by its `id` and its
  parent `invoice_number` on the printed slip. A separate counter can be added later
  if the shop wants one.

This table shape is an **implementation detail presented for the client's review**,
the same way ADR-0017 §5–6 presented the Phase 1 schema additions. It is not frozen
by a further gate; Phase 3's own Definition of Done is the checkpoint.

## New permission code

| code | covers | admin | cashier | step-up |
|---|---|:-:|:-:|:-:|
| `sale.refund_initiate` | start a refund against an existing sale (creates a `pending_approval` row) | ✓ | ✓ | — |
| `sale.refund` *(existing, semantics clarified)* | **approve or reject** a pending refund | ✓ | — | ✓ |

`services/permissions.py` gains `sale.refund_initiate` (Cashier + Admin). `sale.refund`
stays Admin-only and in `STEP_UP_PERMISSIONS`. `flask seed` is idempotent and picks
both up from the catalogue with no migration (the `permission` / `role_permission`
rows are data).

## Still deferred after this gate

- **Voiding a completed sale** — not part of the Phase 3 "returns/refund" step and
  not raised at this gate. Its permission code stays unissued (context.md §4). A void
  before any payment is just discarding an in-progress cart and needs no code.
- **The refund screen's visual design** — the flow and data are specified here;
  the Tailwind/htmx visual layer is deferred with the rest of the UI (context.md
  §4b, Phase 2 UI deviations). O-7's *policy* question is resolved; its *pixels* are
  not, and that is consistent with every other screen so far.
- **Card refunds to card** — reserved `method` value, needs a processor integration.

## Alternatives Considered

- **Keep refunds strictly Admin-only (ADR-0008 §4 as written)** — rejected by the
  client. At a real counter the Cashier is the one facing the customer; making them
  fetch the Admin before anything is even recorded loses the request. Letting the
  Cashier capture the refund while the Admin still authorises the money keeps the
  control and removes the friction.
- **A Cashier value cap for unattended refunds** — offered, not chosen. It adds a
  policy number to argue about and a second authorisation path to build and test,
  for a shop where the Admin is usually on site anyway.
- **Model a refund as a negative `Sale`** — rejected. It would break the
  whole-rupee and `line_total = qty × price` invariants, pollute invoice numbering,
  and make every sales report filter on sign. A dedicated table is clearer.
- **Reuse `credit_ledger_entry` alone** — rejected; it only covers the credit case
  and has nowhere for the cash-drawer refund, the pending state, or the two user ids.
- **Always restock, no damaged-goods flag** — the client's literal answer. Kept as
  the default; the flag is a cheap, flagged superset the client can veto.
- **Split `catalog.manage` now** — rejected by the client; deferred until a manager
  role actually exists.

## Consequences

**Easier:** the Phase 3 build now has an unambiguous refund contract — who, what
state, what fires when, and one transaction boundary. Discounts add zero build.

**Harder:** Phase 3 carries a **new migration** (first since the Phase 1 freeze) and
a two-step refund workflow with a pending state, which is more to build and test than
a one-shot Admin refund would have been. The step-up-on-approval path must be
implemented consistently or it is theatre (ADR-0008's own warning).

**Forecloses:** nothing. A Cashier value cap, a real refund-number counter, card
refunds, and a finer permission split can all be added later without disturbing this
shape.

## Consequential test cases

- Empty-cart checkout is blocked; a refund with no lines selected is blocked
- A refund cannot exceed the sold quantity (or already-refunded remainder) of a line
- A Cashier can initiate a refund but cannot approve one (403 on approve without `sale.refund`)
- An Admin approving a refund without a valid step-up password is refused
- Approving a refund restocks each line whose `restock` is true and skips those where it is false, in one transaction
- A crash between writing `refund` rows and posting stock/ledger effects leaves the refund `pending_approval` and no partial state
- A credit-sale refund posts a negative `credit_ledger_entry` and moves no cash; a cash-sale refund moves cash and posts no ledger entry
- A refund of a `manual_amount` line returns exactly `line_total_paisa`
- A refund of a `manual_weight` / `stepper` line equals the sale line under `round_paisa_to_rupee`
- `sale.status` becomes `partially_refunded` then `refunded` as lines are returned
- A refund entry does not reset the customer's overdue clock (ADR-0015)
- No code path in the sale or refund flow can persist a non-zero discount
