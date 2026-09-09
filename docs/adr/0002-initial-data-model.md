# 0002 — Initial Data Model

Status: **Proposed** — this is the draft the Phase 0 grill-with-docs session exists
to interrogate. It must not become the basis for a migration until that session has
run and the human has approved the field list at the Phase 1 STOP AND ASK gate.
Date: 2026-09-06
Phase: 0

## Context

Every later phase depends on these tables. Once Phase 1's migration is frozen, any
change costs a new migration against a database that may already hold a real shop's
trading history. The Development Specification names ten models; this ADR proposes
their actual shape and, just as importantly, names the places where the shape is
genuinely undecided.

## Decision

### Cross-cutting rules

1. **Money is integer paisa.** Every monetary column is an `Integer` counting paisa
   (1 PKR = 100 paisa) and is named with a `_paisa` suffix. No `Float`, no
   `Numeric`, anywhere, per Operating Rule 8. Formatting to `Rs 6,640` happens only
   at the presentation edge.
2. **Timestamps are UTC**, stored as timezone-aware, converted for display. The shop
   operates in a single timezone (PKT, UTC+5, no DST), but statement-boundary
   correctness is a named edge case and is easier to reason about from a UTC base.
3. **Every mutating record carries `created_at`, and `created_by_user_id`** where a
   person caused it. Attributability is the point of having users at all.
4. **Soft delete, not hard delete**, for anything a historical sale can reference:
   `is_active` plus `deactivated_at`.
5. **No business logic in models.** Models are shape and constraints only;
   calculations live in pure, separately testable functions (Operating Rule 11).

### Tables

**`user`** — id, name, initials, role (`admin` | `cashier`), pin_hash,
password_hash *(nullable, see open question O-1)*, is_active, created_at, last_login_at.

**`category`** — id, name (unique), display_order, is_active.

**`product`** — id, name, sku (unique), barcode (unique, nullable), category_id,
unit_label (e.g. "unit", "bag", "pack", "kg"), cost_price_paisa,
sell_price_paisa, stock_quantity, low_stock_threshold, is_active, created_at,
updated_at.
*`stock_quantity` is the running cached level; `stock_movement` is the truth it is
derived from. The two are written in the same transaction, always.*

**`stock_movement`** — id, product_id, movement_type (`stock_in` | `stock_out` |
`correction` | `sale` | `refund`), quantity_delta (signed), quantity_before,
quantity_after, reason (**required**, non-empty), reference_type + reference_id
(nullable, links a `sale` movement back to its sale), created_by_user_id, created_at.
*Append-only. Rows are never updated or deleted; a mistake is corrected by another
movement.*

**`customer`** — id, name, phone (unique, nullable — see open question O-4), address,
credit_limit_paisa (nullable), credit_terms_days (nullable), balance_paisa (cached),
is_active, created_at, notes.

**`sale`** — id, invoice_number (unique), customer_id (nullable — walk-in),
user_id, terminal_label, subtotal_paisa, discount_paisa, tax_paisa, total_paisa,
payment_method (`cash` | `card` | `credit`), amount_tendered_paisa (nullable, cash
only), change_paisa (nullable, cash only), status (`completed` | `refunded` |
`partially_refunded`), created_at.

**`sale_item`** — id, sale_id, product_id, product_name_snapshot,
unit_price_paisa_snapshot, quantity, line_discount_paisa, line_total_paisa.
*The name and price are snapshotted onto the line. A reprinted receipt from six
months ago must show what was actually charged, not today's price.*

**`payment`** — id, customer_id, sale_id (nullable — a Khata payment settles a
balance, not one invoice), amount_paisa, method (`cash` | `card`), reference,
received_by_user_id, created_at.

**`credit_ledger_entry`** — id, customer_id, entry_type (`credit_sale` | `payment` |
`refund` | `adjustment`), amount_paisa (signed: positive increases what is owed),
balance_after_paisa, sale_id / payment_id (nullable), note, created_by_user_id,
created_at.
*Append-only, same as stock movements. `customer.balance_paisa` is a cache of the
newest row's `balance_after_paisa`.*

**`notification_queue`** — id, customer_id, notification_type (`credit_sale` |
`statement`), dedupe_key (unique — this is what makes duplicate sends impossible),
payload_json, status (`pending` | `sent` | `failed` | `abandoned`), attempt_count,
last_attempt_at, next_attempt_at, last_error, created_at, sent_at.

**`invoice_counter`** — a single-row table holding the next invoice sequence number,
incremented inside the same transaction as the sale via an atomic conditional
update. This is the mechanism that makes concurrent checkouts produce no duplicate
and no skipped invoice numbers.

**`setting`** — key/value store for shop name, address, phone, receipt footer text,
low-stock defaults, backup time. Configuration that the shop owner edits at runtime
lives here; configuration that the deployment owns lives in environment variables,
never here.

## Open questions this ADR cannot settle alone

These are carried into `context.md` and are the substance of the Phase 0 grill.

- **O-1 — PIN vs password.** The Design System (12) mandates PIN quick-switch and
  says it *replaces* any username/password assumption. The Development
  Specification (Phase 1) says hashed passwords. Both cannot be the whole truth.
  Recommendation: PIN is the only till credential, stored with the same Werkzeug
  hashing, with a per-user lockout after repeated failures; an Admin additionally
  holds a longer password for destructive actions. Needs a decision and its own ADR.
- **O-2 — Fractional quantities.** `quantity` is proposed as an integer. A general
  store selling atta or sugar loose cannot express 1.5 kg. Recommendation: store
  quantity as an integer in thousandths of the product's unit, with a per-product
  flag for whether fractional entry is allowed at the till.
- **O-3 — Tax.** The Till mock prints "Tax included" but no tax module exists in the
  feature list. Is there a real GST line, or is the price simply tax-inclusive and
  the label decorative? A `tax_paisa` column is proposed defensively.
- **O-4 — Duplicate customers.** The edge-case matrix says duplicate phone numbers
  are "prevented or flagged". A hard unique constraint prevents two family members
  sharing a number. Recommendation: soft-flag on create, not a database constraint.
- **O-5 — Discounts.** The Till mock shows a per-line "Loyalty discount applied" with
  a struck-through price. No loyalty scheme exists in the feature list. Is this a
  manual per-line discount rendered with friendly wording, or a real rules engine?
  The second would be feature creep requiring its own ADR (Operating Rule 13).
- **O-6 — Credit limit behaviour.** Blocking or warning? Who can override?

## Alternatives Considered

- **Deriving stock level purely from movements, with no cached column** — rejected
  for now. Correct, but every Till scan would sum a product's whole history. The
  cache plus same-transaction write gives the same correctness with a bounded read
  cost; a consistency check that recomputes and compares belongs in the test suite.
- **Storing money as `Numeric(12,2)`** — rejected. SQLite has no true decimal type
  and would store it as text or float underneath, which is exactly the ambiguity
  Operating Rule 8 exists to remove.
- **A single generic `ledger` table for both stock and credit** — rejected. They
  share a shape but not a meaning; merging them would make every query filter on a
  discriminator and make neither easy to read.
- **Hard-deleting products** — rejected outright. It orphans historical sale lines.

## Consequences

**Easier:** append-only movement and ledger tables mean history is never lost and a
disputed balance can always be reconstructed. Snapshotted line items make old
receipts reprintable and correct. Integer paisa removes a whole class of rounding
bugs from billing and Khata maths.

**Harder:** two caches (`product.stock_quantity`, `customer.balance_paisa`) must be
kept in step with their source-of-truth tables, and that discipline has to be
enforced by tests, not by hope.

**Forecloses:** nothing yet — this is deliberately the last cheap moment to change
any of it.
