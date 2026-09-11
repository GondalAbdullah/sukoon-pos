# 0023 — Till Terminal Identification

Status: **Accepted** 2026-09-12 — confirmed by the client
Date: 2026-09-12
Phase: 3 (addendum, after functional sign-off)
Resolves: **O-8** (partially — the labelling half; live terminal status is still open)
Depends on: [ADR-0016](0016-consolidated-data-model.md) (`sale.terminal_label`, already frozen and unused)

## Context

O-8 asked whether the prototype's "Second Till (Terminal 2) — Checking…" Settings
row is a real feature or mock dressing, and was left open. The client has now asked
for "the functionality of multiple tills." Put to the client as a scoped question,
they chose the narrowest of four options: **identify which till rang up each sale**
— not live terminal health-monitoring, and explicitly not independent/offline tills
syncing later (that would contradict ADR-0001's single-host design and was flagged
as needing its own grill session, not chosen).

Multiple simultaneous tills are not new architecture here. ADR-0001 already put
every terminal on the LAN as a browser pointed at the one host's Flask+SQLite
process, and Phase 3 already proved this safe under real concurrency — atomic
invoice-number claiming (`sales_service.claim_invoice_number`, a 50-thread on-disk
test) and a guarded relative stock update (a 30-thread same-product test), both in
`test_invoice_concurrency.py`. `sale.terminal_label` has existed since the
Phase 1 schema freeze and `sales_service.record_sale` already accepts it — nothing
has ever set it. This ADR is about *naming a till*, not building concurrency safety
that already exists.

## Decision

### A till's identity lives in a browser cookie, not the login

A terminal is a property of the **physical PC/browser**, not of whoever is
currently signed in on it — a cashier moving to a different till, or two cashiers
sharing one shift on the same PC, must not rename the till. So the label is stored
in a plain, long-lived cookie (`sukoon_terminal`, 1 year, not part of the signed
Flask session) set once per browser and read on every sale.

**Rejected alternatives:**
- **Ask at login** — rejected. Ties the terminal to the session, not the machine;
  every sign-in would re-ask, and a shared till would get renamed every shift change.
- **Environment variable / server config** — rejected. The Flask process is one
  shared server (ADR-0001); an env var can't distinguish which of several browser
  clients hitting it is which physical till.
- **A `terminal` table with registration** — deferred, not rejected outright; this
  is the shape live health-status (O-8's other half) would need, but there is
  nothing to register or poll yet with only labelling in scope. Revisit if/when
  live status is asked for.

### First use asks once, then remembers

The Till shows a one-time inline prompt — "Name this till" — when the cookie is
absent; once set, it is never asked again on that browser. A small "change" link
next to the till's name in the top bar lets an Admin rename it later (a relabel,
not a re-registration — no server-side record of "known tills" exists).

### Where it shows

`sales_service.record_sale(terminal_label=...)` is finally given the cookie's
value, so every `sale.terminal_label` is populated going forward (existing rows
stay `NULL` — nothing is backfilled or guessed). It appears on the Sale Complete
screen, the receipt (ESC/POS and PDF — both already share one layout function,
so this is one change, not two), and is available wherever a sale is read back.

## Alternatives Considered

(the terminal-identity mechanism alternatives are under "Decision" above, since
they were the actual fork; no separate scope alternative — the four scope options
were put to the client directly.)

## Consequences

**Easier:** a disputed or unusual sale can be traced to a physical till without
guessing. No new table, no migration — the column has existed since Phase 1.

**Harder:** nothing enforces a till's name is unique or meaningful — an Admin could
name two different PCs "Till 1". Acceptable for a single small shop; a `terminal`
table would be the fix if that ever bites.

**Forecloses:** nothing. Live terminal registration/health-status (O-8's other
half) can still be built later as its own table without touching this cookie.

## Consequential test cases

- A fresh browser with no `sukoon_terminal` cookie sees the naming prompt on the Till
- Naming a till sets the cookie and the prompt does not reappear
- A sale rung up after naming carries that `terminal_label`
- The receipt (both ESC/POS bytes and the PDF) shows the till's name
- Renaming a till changes the cookie and future sales, not past ones
