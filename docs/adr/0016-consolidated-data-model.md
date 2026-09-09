# 0016 — Consolidated Data Model

Status: **Accepted** 2026-09-10 — confirmed by the client after review.
Date: 2026-09-10
Phase: 0 (grill-with-docs session 1, closing)
Supersedes: [ADR-0002](0002-initial-data-model.md) in full

## Context

ADR-0002 proposed the original schema. Six later ADRs each amended a piece of it —
quantities (0004), money (0007), authentication (0008), barcodes (0009), catalog
onboarding (0011), product field tiers (0012), customer phone identity (0013),
credit limits (0014), credit terms (0015) — each correctly scoped to its own
decision, each correctly citing what it superseded.

The cost of that correctness is that no single document shows the schema as it
actually stands. A reader opening ADR-0002 today sees a draft with `pin_hash`,
`product.barcode`, `sku NOT NULL`, and a single flat `phone` column — none of which
survive. Phase 1 cannot build a migration by reading twelve documents and mentally
merging them; it needs one.

This ADR is that one document. It changes no decision already made. Where it adds a
column that no prior ADR formalised, that is stated explicitly as a gap found during
consolidation, not a new decision smuggled in.

## Decision

### Gaps found while consolidating, resolved here

Three fields were referenced in the *prose* of an earlier ADR but never written into
an actual schema block anywhere:

1. **`product.created_by_user_id`** — ADR-0011 requires "a name on every" provisional
   product, but no ADR's schema block ever added the column. Added here, nullable
   (a bulk-imported or seeded product may have no creating user).
2. **`credit_ledger_entry.override_authorised_by_user_id`** — ADR-0014 requires the
   authorising Admin's identity to be recorded distinctly from the cashier who rang
   the sale, but only described this as "the id of the Admin" in prose, inside a free
   -text `note`. A fact worth reporting on should not live only in unstructured text.
   Added as its own nullable column, populated only on an override entry.
3. **`notification_queue.notification_type`** gains a third value,
   `'overdue_reminder'`, required by ADR-0015 but never added to the enum ADR-0002
   originally defined as `'credit_sale' | 'statement'`.

### The schema, in full, as it now stands

```
user
  id                    INTEGER PK
  name                  TEXT NOT NULL
  initials              TEXT NOT NULL
  role                  TEXT NOT NULL              -- 'admin' | 'cashier'
  password_hash         TEXT NOT NULL              -- ADR-0008; pin_hash removed
  is_active             BOOLEAN NOT NULL DEFAULT 1
  failed_login_attempts INTEGER NOT NULL DEFAULT 0  -- renamed from failed_pin_attempts
  locked_until          DATETIME NULL
  created_at            DATETIME NOT NULL
  last_login_at         DATETIME NULL

permission                                          -- ADR-0008
  id            INTEGER PK
  code          TEXT NOT NULL UNIQUE
  description   TEXT NOT NULL

role_permission                                     -- ADR-0008
  role            TEXT NOT NULL
  permission_id   INTEGER FK -> permission.id

category
  id              INTEGER PK
  name            TEXT NOT NULL UNIQUE
  display_order   INTEGER NOT NULL DEFAULT 0
  is_active       BOOLEAN NOT NULL DEFAULT 1

product
  id                          INTEGER PK
  name                        TEXT NOT NULL             -- ADR-0012 Tier A
  sku                         TEXT NULL UNIQUE           -- ADR-0012, deferred format (O-17)
  category_id                 INTEGER FK NULL            -- ADR-0012 Tier C
  unit_label                  TEXT NOT NULL DEFAULT 'unit'
  allows_fractional           BOOLEAN NOT NULL DEFAULT 0 -- ADR-0004
  cost_price_paisa            INTEGER NULL               -- ADR-0012 Tier C
  sell_price_paisa            INTEGER NOT NULL           -- ADR-0012 Tier A
  stock_quantity_milli        INTEGER NOT NULL DEFAULT 0 -- ADR-0004, renamed
  low_stock_threshold_milli   INTEGER NULL               -- ADR-0004 + ADR-0012 Tier C
  is_provisional              BOOLEAN NOT NULL DEFAULT 0 -- ADR-0011
  is_active                   BOOLEAN NOT NULL DEFAULT 1
  created_by_user_id          INTEGER FK NULL            -- gap closed here, see above
  created_at, updated_at      DATETIME NOT NULL
  -- product.barcode REMOVED (ADR-0009) -> product_barcode table

product_barcode                                          -- ADR-0009
  id                     INTEGER PK
  product_id             INTEGER FK -> product.id
  barcode                TEXT NOT NULL UNIQUE
  price_override_paisa   INTEGER NULL      -- NULL = product.sell_price_paisa
  label                  TEXT NULL
  is_active              BOOLEAN NOT NULL DEFAULT 1
  created_by_user_id     INTEGER FK -> user.id
  created_at             DATETIME NOT NULL

stock_movement
  id                    INTEGER PK
  product_id            INTEGER FK -> product.id
  movement_type         TEXT NOT NULL       -- 'stock_in'|'stock_out'|'correction'|'sale'|'refund'
  quantity_delta_milli  INTEGER NOT NULL    -- ADR-0004, renamed, signed
  quantity_before_milli INTEGER NOT NULL    -- ADR-0004, renamed
  quantity_after_milli  INTEGER NOT NULL    -- ADR-0004, renamed
  reason                TEXT NOT NULL       -- CHECK length > 0
  reference_type        TEXT NULL
  reference_id          INTEGER NULL
  created_by_user_id    INTEGER FK -> user.id
  created_at            DATETIME NOT NULL

customer
  id                          INTEGER PK
  name                        TEXT NOT NULL
  phone_raw                   TEXT NULL          -- ADR-0013, replaces flat `phone`
  phone_normalised             TEXT NULL          -- ADR-0013, matching/delivery key
  address                     TEXT NULL
  credit_limit_paisa          INTEGER NULL       -- ADR-0014; NULL = unenforced
  credit_terms_days           INTEGER NULL       -- ADR-0015; NULL = untracked
  balance_paisa               INTEGER NOT NULL DEFAULT 0   -- cache
  phone_verified              BOOLEAN NOT NULL DEFAULT 0   -- ADR-0013
  phone_verified_at           DATETIME NULL
  phone_verified_method       TEXT NULL          -- 'shown'|'called'|'otp' (O-18)
  phone_verified_by_user_id   INTEGER FK NULL
  is_active                   BOOLEAN NOT NULL DEFAULT 1
  created_at                  DATETIME NOT NULL
  notes                       TEXT NULL

sale
  id                      INTEGER PK
  invoice_number          TEXT NOT NULL UNIQUE
  customer_id              INTEGER FK NULL     -- NULL = walk-in
  user_id                  INTEGER FK -> user.id
  terminal_label           TEXT NULL
  subtotal_paisa           INTEGER NOT NULL
  discount_paisa           INTEGER NOT NULL DEFAULT 0  -- ADR-0008, fixed at zero in v1
  tax_paisa                INTEGER NOT NULL DEFAULT 0  -- ADR-0008 addendum, fixed at zero
  total_paisa               INTEGER NOT NULL
  payment_method            TEXT NOT NULL       -- 'cash'|'card'|'credit'
  amount_tendered_paisa    INTEGER NULL        -- cash only
  change_paisa              INTEGER NULL        -- cash only
  status                    TEXT NOT NULL       -- 'completed'|'refunded'|'partially_refunded'
  created_at                DATETIME NOT NULL

sale_item
  id                          INTEGER PK
  sale_id                     INTEGER FK -> sale.id
  product_id                  INTEGER FK -> product.id
  product_barcode_id          INTEGER FK NULL    -- ADR-0009, which label produced the price
  product_name_snapshot       TEXT NOT NULL
  unit_price_paisa_snapshot   INTEGER NOT NULL
  quantity_milli               INTEGER NOT NULL   -- ADR-0004, renamed
  quantity_source              TEXT NOT NULL       -- ADR-0005:
                                                    -- 'stepper'|'manual_weight'|'manual_amount'
                                                    -- reserved: 'usb_scale'|'scale_label'
  line_discount_paisa          INTEGER NOT NULL DEFAULT 0   -- fixed at zero in v1
  line_total_paisa             INTEGER NOT NULL   -- ADR-0007: authoritative on
                                                    -- manual_amount lines, computed otherwise

payment
  id                      INTEGER PK
  customer_id              INTEGER FK -> customer.id
  sale_id                   INTEGER FK NULL
  amount_paisa              INTEGER NOT NULL
  method                    TEXT NOT NULL       -- 'cash'|'card'
  reference                 TEXT NULL
  received_by_user_id       INTEGER FK -> user.id
  created_at                 DATETIME NOT NULL

credit_ledger_entry
  id                                INTEGER PK
  customer_id                        INTEGER FK -> customer.id
  entry_type                         TEXT NOT NULL   -- 'credit_sale'|'payment'|'refund'|'adjustment'
  amount_paisa                       INTEGER NOT NULL  -- signed
  balance_after_paisa                 INTEGER NOT NULL
  sale_id                             INTEGER FK NULL
  payment_id                          INTEGER FK NULL
  override_authorised_by_user_id      INTEGER FK NULL   -- gap closed here, ADR-0014
  note                                 TEXT NULL
  created_by_user_id                  INTEGER FK -> user.id
  created_at                          DATETIME NOT NULL

notification_queue
  id                  INTEGER PK
  customer_id          INTEGER FK -> customer.id
  notification_type    TEXT NOT NULL    -- 'credit_sale'|'statement'|'overdue_reminder'
                                          -- gap closed here, ADR-0015
  dedupe_key           TEXT NOT NULL UNIQUE
  payload_json         TEXT NULL
  status               TEXT NOT NULL     -- 'pending'|'sent'|'failed'|'abandoned'
  attempt_count         INTEGER NOT NULL DEFAULT 0
  last_attempt_at       DATETIME NULL
  next_attempt_at       DATETIME NULL
  last_error            TEXT NULL
  created_at             DATETIME NOT NULL
  sent_at                DATETIME NULL

invoice_counter
  id             INTEGER PK    -- always 1
  prefix         TEXT NOT NULL
  year           INTEGER NOT NULL
  next_sequence  INTEGER NOT NULL

setting
  key           TEXT PK
  value         TEXT NULL
  updated_at    DATETIME NOT NULL
```

**Fifteen tables**, up from the "eleven" ADR-0002 originally counted (itself already
corrected to twelve during session 1): `permission`, `role_permission`, and
`product_barcode` are net new; nothing has been removed.

### Nullable-threshold behaviour, stated explicitly

`product.low_stock_threshold_milli = NULL` means no low-stock check runs for that
product — mirroring the pattern already established for `credit_limit_paisa` and
`credit_terms_days`: a null column disables its check rather than defaulting to zero
and firing constantly. A newly created or provisional product therefore never
triggers a low-stock alert until an Admin sets a real threshold.

### Invoice counter behaviour, decided on review, 2026-09-10

The table shape (`year` and `next_sequence` on one row) already supports either a
continuous counter or a yearly-resetting one; the behaviour was not yet decided.
**Decision: the sequence resets to 1 on the first sale of a new calendar year.**
`INV-2024-0413`, then `INV-2025-0001`. This matches the format shown in the
prototype's own mock and how a paper invoice book already works here — reasoning
enough on its own, without needing a fresh grill session over a display convention.

Concretely, the same atomic claim that increments `next_sequence` first checks
whether the counter's stored `year` still matches the current year; if not, it
resets `next_sequence` to 1 and updates `year`, inside the same transaction that
claims the number — so two terminals racing to make the first sale of January 1st
still cannot collide. Implementation is Phase 3's; the policy is decided here.

## Alternatives Considered

- **Leaving ADR-0002 as the living document, edited in place** — rejected. The
  standards this project follows are explicit that a decision record is not quietly
  rewritten; a superseding decision gets its own record, and the original is marked
  Superseded and left as history. ADR-0002's body is untouched; only its Status
  header changes.
- **Silently adding the three closed gaps without flagging them as gaps** — rejected.
  Each is a real thing no prior ADR actually decided as a column; naming them as
  found-while-consolidating rather than folding them in as if always planned is the
  honest-reporting standard this project holds itself to.

## Consequences

**Easier:** Phase 1's migration has exactly one document to build against. Every
field's justification is traceable to its owning ADR without cross-referencing
twelve files by hand.

**Harder:** none beyond the one-time cost of writing this.

**Forecloses:** nothing. Further amendments follow the same pattern — a new ADR,
citing what it supersedes here.

## Consequential test cases

- Every table in this ADR has a corresponding SQLAlchemy model before Phase 1 closes
- A migration generated from these models applies cleanly to an empty database
- `product.low_stock_threshold_milli = NULL` never fires a low-stock alert
- `notification_queue.notification_type` accepts all three values, rejects a fourth
- `credit_ledger_entry.override_authorised_by_user_id` is populated only on an override entry
- The first sale of a new calendar year resets the sequence to 1 and updates `year`
- Two terminals racing on the year's first sale still produce no duplicate number
