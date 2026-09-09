# 0014 — Credit Limit Enforcement

Status: **Accepted**
Date: 2026-09-10
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0008](0008-authentication-and-access-control.md)
Resolves: O-6

## Context

The Khata mock flags Malik Zahid Enterprise coral, labelled "Near credit limit", and
`customer.credit_limit_paisa` was proposed nullable in ADR-0002. Neither the
Development Specification's feature list (6.E) nor its edge-case matrix mentions a
limit at all. Under ADR-0006 rule 4, a design mock cannot create technical scope by
itself — so whether this is real, and if so how it behaves, needed asking rather than
assuming.

Confirmed with the client on 2026-09-10: credit limits are real, per customer, and
the recommended enforcement — block for a Cashier, Admin may override with step-up,
the override is recorded — is accepted.

## Decision

`customer.credit_limit_paisa` remains nullable. **NULL means no limit is enforced**;
no check runs for such a customer at all.

When a credit sale would take `customer.balance_paisa + sale.total_paisa` above a
non-null limit:

- **A Cashier is blocked.** The sale cannot complete as credit. They may switch the
  sale to cash or card, or ask an Admin to authorise it.
- **An Admin may override**, and doing so requires the same step-up
  re-authentication as any other destructive action under ADR-0008 — the limit
  exists specifically to be a deliberate decision, not a default that a shared
  session quietly bypasses.
- **The override is recorded.** The resulting `credit_ledger_entry` carries a note
  identifying it as an over-limit override and the id of the Admin who authorised it,
  distinct from the cashier who rang the sale (already captured as
  `sale.user_id`). A month later, "who let this go over" is answerable from the
  ledger alone.

The check compares against the limit **after** the sale, not before — a customer
exactly at their limit can still make a purchase that would take them to the limit,
but not past it.

## Alternatives Considered

- **Warn only, never block** — rejected. A limit that never stops a sale is
  decoration, and unlimited cashier-extended credit is a real way a shop loses money.
- **Hard block, no override** — rejected. It refuses a sale over a number the owner
  might happily waive for a trusted long-standing customer, with no way to honour
  that judgement at the counter.
- **Override without step-up** — rejected. It would make the limit meaningless for
  any Cashier who simply asks the Admin to click a button rather than genuinely
  re-authorise.
- **No credit limit feature at all** — rejected by the client; it is a real,
  wanted control, not mock dressing in this instance.

## Consequences

**Easier:** the owner's judgement stays in the loop for exactly the moments it
matters, and every override leaves a named, timestamped trail.

**Harder:** if the Admin is not physically present, a Cashier genuinely cannot
complete an over-limit credit sale — the customer must pay differently, or wait.
This is the accepted cost of the control, not an oversight.

**Forecloses:** nothing.

## Consequential test cases

- A credit sale that would stay within the limit succeeds normally for a Cashier
- A credit sale that would exceed the limit is blocked for a Cashier
- The same sale succeeds for an Admin only after step-up re-authentication
- An override records both the authorising Admin and the ringing Cashier distinctly
- A customer with a null credit limit is never blocked
- The check compares balance after the prospective sale, not before it
