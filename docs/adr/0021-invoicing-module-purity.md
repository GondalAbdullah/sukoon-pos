# 0021 — `invoicing.py` Stays Pure; the Atomic Claim Lives in `sales_service`

Status: **Accepted** 2026-09-11 — confirmed by the client
Date: 2026-09-11
Phase: 3
Clarifies: [ADR-0003](0003-module-boundaries.md) (§3 and the module-list gloss)

## Context

ADR-0003 contradicts itself on one module. Its module list annotates
`invoicing.py` as *"pure: invoice number formatting **+ atomic allocation**"*,
while rule 3 states that `pricing.py` and `invoicing.py` are *"pure — deterministic
functions over plain values, **no I/O**"*. Claiming the next invoice number from
the `invoice_counter` row is inherently I/O, so both cannot hold.

## Decision

**Rule 3 wins.** `invoicing.py` contains only pure functions —
`format_invoice_number` and `compute_next_counter` (the yearly-reset arithmetic).
The one database touch, the atomic `UPDATE invoice_counter … RETURNING` that claims
a number, lives in **`sales_service.claim_invoice_number`**, where it also belongs
transactionally: the claim must be part of the same transaction as the sale it
numbers, so that a rolled-back sale releases the number (ADR-0016).

The module-list gloss in ADR-0003 is treated as imprecise wording, not a second
decision. ADR-0003's tree is otherwise unchanged; no file is added or removed.

## Alternatives Considered

- **Let `invoicing.py` do the one DB write** — matches the gloss literally, but
  breaks the mechanically-valuable "these two modules are pure" guarantee for a
  three-line wrapper, and splits the sale transaction across two modules.
- **A new `services/invoice_counter.py`** — a whole module for one function; the
  claim already needs to sit inside `sales_service`'s transaction.

## Consequences

**Easier:** `invoicing.py` stays exhaustively unit-testable with no fixtures; the
sale transaction is defined in one place.

**Harder:** nothing. **Forecloses:** nothing.
