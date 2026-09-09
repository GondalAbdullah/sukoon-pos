# 0008 — Authentication and Access Control

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0006](0006-document-authority.md)
Supersedes: the `pin_hash` credential proposed in ADR-0002
Overrides: Design System 6 (Figure 1) and 12, on the credential only

## Context

The two governing documents disagreed on how a person gets into the till.

- **Development Specification 6.A** — "Login/logout with hashed passwords,
  session-based auth", two roles, "Basic Admin/Cashier **with an extensible
  permissions table underneath**", and Cashier routes hard-blocked at the server
  with a real 403.
- **Design System 12** — Phase 1 must implement PIN quick-switch, and this
  "replaces any generic username/password assumption."

ADR-0006 ranks the Development Specification above the Design System on technical
matters, and a credential is a technical matter. The client confirmed the direction
explicitly on 2026-09-08.

Separately, the Development Specification is silent on four things a real shop needs:
what exactly is Admin-only, brute-force protection, step-up re-authentication, and
who may refund. It defers the last of these, by name, to the Phase 3 STOP AND ASK
gate.

## Decision

### 1. Passwords, for everyone. No PIN.

Every user authenticates with a password, hashed with Werkzeug and carried in a
Flask-Login session. `user.pin_hash` is removed from the model entirely;
`user.password_hash` is `NOT NULL`.

The `failed_attempts` / `locked_until` columns are kept, and lockout is implemented:
the Development Specification never asked for brute-force protection, but a login
form with no attempt limit is a defect regardless of who specified it.

### 2. The login screen changes, and this is a recorded design deviation

The Design System's login screen (Figure 1) is a row of staff avatars above a
numeric PIN pad. A PIN pad cannot enter a password, so the screen must change.

**What is kept:** the avatar row, the time-of-day greeting, the calm radial wash, the
quiet status line, the whole visual language.
**What changes:** selecting an avatar reveals a password field instead of a numeric
keypad. Selection is still one tap; the auto-submit-on-fourth-digit behaviour
disappears, replaced by an explicit submit.

Per Design System 13, this deliberate deviation from a reference screenshot is
recorded in `context.md`. The Design System document itself is not edited — ADR-0006
rule 1 says the losing document is not rewritten, the override is recorded here.

### 3. A permission table exists from Phase 1

As the Development Specification chose in 7 ("an extensible permissions table
underneath... allows RBAC to be added later without a rewrite"). ADR-0002 proposed
only a plain `user.role` enum and therefore failed to implement a decision the
specification had already made. Corrected here.

```sql
permission          (id, code TEXT UNIQUE, description TEXT)
role_permission     (role TEXT, permission_id FK)     -- seeded: 'admin', 'cashier'
```

Roles stay a closed set of two in v1. Authorisation is always checked against a
**permission code**, never against `role == 'admin'` written inline at a call site.
That indirection is the entire point: adding a third role later is then a data
change, not a code change.

### 4. Admin-only actions, as confirmed

| Action | Who |
|---|---|
| Edit a product's selling price | **Admin only** |
| Process a refund or return | **Admin only** |
| Ring up a sale, take payment, scan | Cashier and Admin |

Every Admin-only action is enforced server-side and returns **403**, per the
Development Specification's own edge case. A hidden button is not access control.

Actions **not yet assigned** and deferred to the Phase 3 gate, where the
specification already places them: voiding a completed sale, creating or deleting a
product, performing stock-in and stock-out, adjusting a Khata ledger entry, recording
a Khata payment, exporting data. These are listed rather than silently defaulted.

### 5. Step-up re-authentication for destructive actions

Being logged in as Admin is not sufficient for an action that rewrites history. The
password must be re-entered at the moment of the action.

Applies to: refunds, editing a sell price, and — once assigned above — voiding a sale
and adjusting a ledger entry.

This exists for a specific, realistic failure: the owner logs in, walks away, and the
terminal sits unattended as Admin on a shop floor. Role checks alone do nothing
about that; re-authentication does. It costs the owner one password entry on the rare
occasions he does these things, and nothing at all on a normal day.

### 6. No discount mechanism is built

Confirmed by the client: there are no explicit discounts. The prototype's
"Loyalty discount applied" and struck-through price are mock dressing, and per
ADR-0006 rule 4 a design mock cannot create technical scope.

`sale.discount_paisa` and `sale_item.line_discount_paisa` are retained as columns
fixed at zero, because refunds and future price-correction flows benefit from the
shape existing, and a zero column costs nothing. No UI, no service function, and no
route may set them in v1.

A reduced price is instead handled by relabelling the goods with a new barcode at the
lower price. The data model for that is a separate decision, taken next in this
session.

## Alternatives Considered

- **PIN as specified by the Design System** — rejected by the client. It is faster and
  better suited to a touch terminal, but four digits protect Admin actions poorly and
  are trivially shoulder-surfed at a counter.
- **PIN for cashiers, password for Admin** — rejected. Two credential systems to
  build, test, and explain, for a shop with a handful of staff.
- **Role checks written inline as `if user.role == 'admin'`** — rejected. It is what
  the specification's "extensible permissions table" exists to avoid, and it scatters
  authorisation across every call site.
- **Step-up at login instead of at the action** — rejected. It penalises every login
  to defend against a rare event, which is how a control gets disabled by the people
  it protects.
- **Building a discount engine anyway, since the mock shows one** — rejected under
  Operating Rule 13 and ADR-0006 rule 4.
- **Dropping the discount columns entirely** — rejected. Refunds and corrections may
  need a negative adjustment on a line, and adding a column later is a migration
  against live trading data.

## Consequences

**Easier:** one credential type. Authorisation is centralised behind permission
codes, so a new role is a seed change. The unattended-Admin-terminal risk is closed.

**Harder:** the login screen no longer matches its reference screenshot, so the
design DoD's side-by-side check must consult this ADR. Step-up adds a re-entry step
to destructive actions, which must be implemented consistently or it is theatre.

**Forecloses:** nothing. A PIN could be reintroduced later as an alternative
credential without disturbing the permission model.

## Consequential test cases

- A Cashier session hitting every Admin-only route receives 403, not a redirect
- Authorisation is denied when a permission code is absent, even for role `admin`
- Repeated failed logins lock the account, and the lock expires correctly
- A destructive action without a fresh step-up re-entry is refused
- A step-up entry authorises exactly one action, and does not persist in the session
- No code path anywhere can set a non-zero discount in v1
- Session expiry mid-sale does not lose the cart
