# 0003 — Module Boundaries

Status: **Proposed** — awaiting the Phase 0 grill-with-docs session. The
Development Specification's Phase 0 STOP AND ASK gate requires the human to confirm
this module list, with no additions or removals, before coding begins.
Date: 2026-09-06
Phase: 0

## Context

Operating Rule 11 requires business logic to stay out of route handlers and to be
unit-testable in isolation from Flask. The "Building Software the Right Way"
standard adds the shape every feature should repeat: schema, then pure logic, then
thin routes, then UI, then two tiers of tests. That only works if the boundaries
are drawn once, up front, and then not renegotiated per feature.

## Decision

```
sukoon/
  app.py                  # application factory, blueprint registration
  config.py               # environment-driven config; no secrets in code
  extensions.py           # db, migrate, login_manager singletons
  models/                 # SQLAlchemy models only: shape + constraints
  services/               # ALL business logic. No Flask imports permitted here.
    auth_service.py
    inventory_service.py
    pricing.py            # pure: discounts, line totals, cart totals
    sales_service.py
    invoicing.py          # pure: invoice number formatting + atomic allocation
    khata_service.py      # credit ledger + balance maths
    notifications/
      queue.py
      providers/          # provider adapter interface + implementations
    reporting_service.py
    receipts/             # ESC/POS builder + PDF fallback
    backup_service.py
  routes/                 # thin blueprints: parse, call a service, render
    till.py  stock.py  khata.py  insights.py  settings.py  auth.py
  templates/              # Jinja2, matching the Design System screen-for-screen
  static/
    css/tailwind.css      # compiled, purged; the only stylesheet shipped
    fonts/                # Inter woff2, bundled locally
    icons/                # only the Lucide SVGs actually used
    img/brand/
  jobs/                   # APScheduler job definitions
tests/
  pure/                   # no database, no network
  integration/            # real temp SQLite, real routes, no mocks
```

### The rules that make the boundary real

1. **`services/` never imports Flask.** Enforced mechanically by a lint rule or a
   test that greps the package, not by review discipline. This is what keeps the
   business logic genuinely unit-testable.
2. **`routes/` never contains a calculation.** A route parses input, calls one
   service function, and renders. If a route needs an `if` about money or stock, it
   belongs in a service.
3. **Modules named `pricing.py` and `invoicing.py` are pure** — deterministic
   functions over plain values, no I/O. They carry the arithmetic most likely to be
   wrong and most cheaply tested.
4. **Function naming follows the taxonomy** from the standards reference:
   `resolve_*` looks something up, `compute_*` is a pure calculation with no side
   effects, `validate_*_input` checks before anything is trusted, `clamp_*`
   defensively bounds a value.
5. **Every meaningful failure gets its own named error class** ending in `Error`
   (`InsufficientStockError`, `CreditLimitExceededError`, `DuplicateBarcodeError`),
   defined beside the service that raises it, so a route can map each to a precise
   status and a calm, plain-language message.
6. **A secondary action never breaks a primary one.** Enqueuing a WhatsApp
   notification, writing an analytics row, or firing a print job cannot raise into
   the sale transaction. This is tested by injecting a failure, not assumed.

## Alternatives Considered

- **Feature-sliced packages** (`sukoon/khata/{models,service,routes}.py`) — a real
  and defensible alternative that keeps a feature's files together. Rejected
  because the layer boundary between "logic" and "Flask" is the one this project
  most needs enforced, and a layered tree makes a violation visible at a glance.
- **Logic directly in route handlers** — rejected by Operating Rule 11.
- **A repository/unit-of-work layer between services and SQLAlchemy** — rejected as
  premature. SQLAlchemy's session already is a unit of work; a second abstraction
  over a single-database application buys indirection, not testability.

## Consequences

**Easier:** every feature looks the same, so a new contributor finds anything by
knowing the pattern. The pure modules can be tested exhaustively at boundary
conditions with no fixtures at all.

**Harder:** a feature's code lives in four directories rather than one, so a change
touches more files.

**Forecloses:** nothing structural. Splitting into feature packages later is a
mechanical move if the layer discipline held.
