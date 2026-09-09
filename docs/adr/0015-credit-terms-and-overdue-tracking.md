# 0015 — Credit Terms and Overdue Tracking

Status: **Accepted**
Date: 2026-09-10
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0002](0002-initial-data-model.md) (credit_ledger_entry, append-only)
Affects: Phase 4 (Khata), Phase 5 (WhatsApp)
Scope note: this is a **client-added requirement**, present in neither governing
document. The Development Specification's WhatsApp feature (6.F) names only
credit-sale notification and monthly statements — nothing about overdue detection or
a chasing reminder. Recorded under Operating Rule 13 rather than absorbed silently.

## Context

The Khata mock shows "Credit terms: 30 days" as a per-customer field. Confirmed with
the client on 2026-09-10: this is real policy, not display text. An overdue account
should be flagged, and chased with a WhatsApp reminder — the UI's implication was
correct.

That answers *whether* this is built. It does not yet answer *how "overdue" is
computed*, and the two honest answers are genuinely different features.

The Khata ledger (ADR-0002) is a running balance: `credit_ledger_entry` rows are
append-only `credit_sale` / `payment` / `refund` / `adjustment` entries, and
`customer.balance_paisa` is their cumulative sum. There is no per-invoice due date,
because a customer typically buys repeatedly and pays down the total irregularly,
not one purchase at a time.

"30 days" naturally applies to a single unpaid purchase, not to a lump balance. So
the real question is: **when a customer makes partial payments against an
accumulating balance, which specific purchase does that payment settle?** The answer
decides whether "overdue" means something precise and per-purchase, or something
simpler and account-wide.

## Decision — settled

- `customer.credit_terms_days` is real, nullable. NULL means no terms are tracked for
  that customer and no overdue check runs, exactly mirroring how a null credit limit
  disables ADR-0014's check.
- An overdue account is **flagged** — visible in the Khata list, consistent with how
  a near-limit balance is already flagged coral in the mock.
- An overdue account is **chased with a WhatsApp reminder**, via the same
  `notification_queue` mechanism as a credit-sale notification (ADR-0002), so it
  inherits the existing guarantee that a down provider never blocks anything —
  in this case, never blocks the reminder job from completing its sweep, not a sale.
- **A reminder is sent only to a verified number** (ADR-0013). An unverified number
  is flagged in the UI the same way, but receives no financial detail, consistent
  with the rule already established there.
- This is a **new scheduled job**, distinct from monthly statement generation,
  running in-process via APScheduler per the existing stack (ADR-0001). It sweeps
  overdue accounts on a cadence still to be set (daily is the working assumption).

## Decision — the aging method, confirmed 2026-09-10

**Account-level staleness**, not per-purchase FIFO allocation. The client accepted
the recommendation.

### The precise, buildable rule

```
reference_date(customer) =
    the created_at of the customer's most recent
    credit_ledger_entry where entry_type = 'payment'
    if one exists,
  else
    the created_at of the customer's first
    credit_ledger_entry where entry_type = 'credit_sale'
    (the date they first went into debt at all)

is_overdue(customer, now) =
    customer.balance_paisa > 0
    and (now - reference_date(customer)).days > customer.credit_terms_days
```

A pure function, `compute_overdue_status(ledger_entries, credit_terms_days, now) ->
OverdueStatus(is_overdue: bool, reference_date: datetime, days_overdue: int)`,
taking already-fetched ledger rows and returning a value the Khata list can badge
directly ("14 days overdue") without a second query.

**Only an entry_type of `payment` resets the clock.** A `refund` or an `adjustment`
does not, even though both can reduce `balance_paisa`. The reasoning: overdue tracking
exists to answer "has this customer actually paid something recently", and a refund
or a correction is not the customer paying — it is the shop crediting them back or
fixing its own record. Counting either as payment activity would let an unrelated
correction silently reset a genuinely stale account's clock.

**What this method does not do**, stated plainly since it was the reason FIFO was
rejected: it does not know which specific purchase is unpaid, only that the account
as a whole is in debt and has gone quiet. A customer who buys constantly and pays
irregularly is judged on their most recent payment, not on their oldest unpaid item.
That is the deliberate trade for not needing a settlement table.

**A consequence worth stating so it is never mistaken for a bug:** any payment,
however small, resets the clock to today. A customer paying Rs 50 against a
Rs 40,000 balance clears their overdue flag for a full `credit_terms_days` again.
This is accepted as correct for v1 — it rewards any sign of engagement, which is a
defensible reading of "chasing" a customer, and it is far simpler than a rule that
tries to judge whether a payment was "enough".

## Alternatives Considered

- **No overdue tracking at all, terms as display only** — rejected; the client
  confirmed it is real behaviour.
- **FIFO allocation (design A)** — rejected. It is the more precise, accountant's
  reading of "30 days", but it requires a new table recording which payment settled
  which purchase, and correctly, since money is involved. Judged not worth the
  implementation weight for a shop whose real practice is closer to "chase the
  balance" than "chase this specific invoice."
- **Refund or adjustment entries also resetting the clock** — rejected. Neither
  reflects the customer paying something; counting them would let an unrelated
  correction mask a genuinely stale account.
- **Reusing the monthly statement job for reminders** — rejected. They run on
  different triggers (calendar month vs. days-since-payment) and a coupled job would
  need to know about both cadences regardless.

## Consequences (of what is settled)

**Easier:** the reminder inherits the existing notification-queue guarantees for
free — no blocking, no duplicate sends, graceful handling of a missing or unverified
number.

**Harder:** a second scheduled job now exists alongside the monthly statement job,
and both must be reasoned about together for overlap (a customer overdue and due a
statement in the same week should not receive two uncoordinated messages — this is
tracked as a sub-item, not yet resolved).

**Forecloses:** nothing yet, pending the open decision above.

## Consequential test cases

- A customer past their credit terms with an outstanding balance is flagged
- A customer with a null `credit_terms_days` is never flagged, regardless of balance
- A fully paid customer, even if once overdue, is not flagged
- A customer with a balance and no payment yet is aged from their first credit sale
- A payment resets the reference date to that payment's own timestamp
- A refund does not reset the reference date, even though it reduces the balance
- An adjustment does not reset the reference date, even though it changes the balance
- `days_overdue` matches a hand-calculated value for a known fixture
- An overdue reminder goes only to a verified number; an unverified one gets nothing
- The overdue sweep completes normally when the WhatsApp provider is unreachable
