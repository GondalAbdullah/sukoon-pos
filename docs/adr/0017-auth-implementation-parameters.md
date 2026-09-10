# 0017 — Auth Implementation Parameters

Status: **Accepted** 2026-09-10
Date: 2026-09-10
Phase: 1
Depends on: [ADR-0008](0008-authentication-and-access-control.md), [ADR-0016](0016-consolidated-data-model.md)

## Context

ADR-0008 decided *what* the authentication model is: passwords for everyone, a
permission table checked by code, lockout on repeated failures, step-up for
destructive actions. It deliberately did not pin the numbers and strings needed to
actually build it. Phase 1 has to choose them, and they should be written down
once rather than discovered by reading the code.

None of what follows is costly to reverse — the numbers are configuration, the
permission rows are seed data — so this is a short record of choices, not a
grill-flagged decision.

## Decision

### 1. The v1 permission catalogue

Only the permissions ADR-0008 §4 *confirmed* are seeded. The codes:

| code | description | admin | cashier |
|---|---|:-:|:-:|
| `sale.ring` | Ring up a sale, add items to a cart | ✓ | ✓ |
| `sale.take_payment` | Take cash / card / credit payment | ✓ | ✓ |
| `product.scan` | Resolve a scanned barcode at the till | ✓ | ✓ |
| `product.create_provisional` | Create a provisional product at the till (ADR-0011) | ✓ | ✓ |
| `product.edit_price` | Edit a product's selling price — step-up | ✓ | — |
| `sale.refund` | Process a refund / return — step-up | ✓ | — |

`sale.refund` and `product.edit_price` are the two codes in `STEP_UP_PERMISSIONS`.
`Admin` holds every code by construction (`set(PERMISSIONS)`), so a new Admin-only
code is automatically granted; `Cashier` holds an explicit subset.

Actions ADR-0008 §4 **defers to the Phase 3 gate** (void a sale, create/delete a
product, stock-in/out, adjust a ledger entry, record a Khata payment, export data)
get their codes when that gate decides them — not now. Seeding a code before the
policy exists would be guessing.

The catalogue lives in `sukoon/services/permissions.py` as plain data and is
written to the `permission` / `role_permission` tables by `flask seed`, which is
idempotent. `seed_permissions()` is reference data every environment runs; the dev
users and sample catalogue are separate and dev-only.

### 2. Lockout parameters (config, not schema)

| setting | default | meaning |
|---|---|---|
| `LOGIN_MAX_ATTEMPTS` | 5 | consecutive failures before a lock |
| `LOGIN_LOCKOUT_MINUTES` | 15 | how long the lock lasts |

The counter increments on each wrong password and is **not** reset by time — only a
successful login clears it. The lock itself is time-boxed: once `locked_until` is in
the past, the next attempt is allowed and, if correct, clears everything. A locked
account returns **429** from `/login`; a wrong credential returns **401**. A missing
user and a wrong password are reported identically so the form cannot enumerate
accounts. `compute_lockout()` is a pure function, boundary-tested.

### 3. Session lifetime

`PERMANENT_SESSION_LIFETIME` defaults to **600 minutes** (10 hours — one long
shift), refreshed on each request, overridable via `SESSION_LIFETIME_MINUTES`.
ADR-0008 §5's step-up requirement means a stale-but-live session still cannot
perform a destructive action without a fresh password, so the lifetime is a
convenience bound, not the security boundary.

### 4. Login identifier

The login form takes a **name or initials** (case-insensitive), not an email —
the shop has no email addresses for staff, and the reference screen selects a
person, not types an address. `user.name` and `user.initials` are both matched.

### 5. `role_permission` carries a surrogate primary key

ADR-0016's schema block lists `role_permission` as `(role, permission_id)` with no
explicit key. The model adds an `id INTEGER PK` and enforces the real constraint
with a `UNIQUE(role, permission_id)`. A surrogate key on a pure join table is a
mechanical implementation choice; the uniqueness guarantee ADR-0016 intended is
unchanged. Flagged to the human at the Phase 1 schema-freeze gate for the record.

### 6. CHECK constraints added at model level

Named CHECKs not spelled out in ADR-0016 but implied by its prose:
`product.sell_price_paisa >= 0`, `product.cost_price_paisa IS NULL OR >= 0`,
`length(trim(product.name)) > 0`, `length(trim(stock_movement.reason)) > 0` (the
last is ADR-0016's own `CHECK length > 0` note). Also flagged at the freeze gate.

## Alternatives Considered

- **Seeding every conceivable permission code now** — rejected. ADR-0008 explicitly
  parked six action-groups for the Phase 3 gate; inventing their codes and role
  assignments here would pre-empt that decision.
- **A composite primary key on `role_permission`** — defensible and arguably purer,
  but Flask-Migrate/Alembic batch migrations on SQLite are smoother with a single
  surrogate key, and every other table in the schema uses one.
- **Storing lockout parameters in the `setting` table instead of config** — rejected
  for v1. They are operational tuning an installer sets, not something a shop user
  changes from a screen; `setting` is for the latter.
- **Email/username login** — rejected, no email exists for shop staff.

## Consequences

**Easier:** every parameter has one home and one rationale. Adding an Admin-only
permission is a one-line dict change plus a re-seed. The pure `compute_lockout`
keeps the one piece of arithmetic here fully testable.

**Harder:** nothing material. The deferred permission codes mean Phase 3 must
remember to seed them when it assigns them — noted in `context.md`.

**Forecloses:** nothing. A third role, a `setting`-driven lockout, or a composite
key are all still reachable without disturbing what is built.

## Consequential test cases

- The seeded catalogue has exactly the six codes above with the stated role split
- `seed_permissions()` run twice produces no duplicate rows
- Lockout engages at the 5th failure and a past `locked_until` does not block
- `/login` returns 401 for a bad credential and 429 for a locked account
- A Cashier hitting `/admin/price-check` gets 403; an anonymous user is redirected
- Even role `admin` is denied `product.edit_price` if the `role_permission` row is absent
