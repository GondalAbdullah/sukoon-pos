# 0029 — Message Delivery: What "Sent" Means, Retries, Giving Up, and Pausing

Status: **Accepted** 2026-09-14 — Phase 5 grill session
Date: 2026-09-14
Phase: 5
Amended by: [ADR-0032](0032-payment-receipt-message.md) (adds the payment receipt as a fifth message type)
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D3, §D4
Depends on: [ADR-0001](0001-technology-stack.md), [ADR-0003](0003-module-boundaries.md) §6, [ADR-0016](0016-consolidated-data-model.md) (`notification_queue`), [ADR-0027](0027-whatsapp-provider-and-account.md), [ADR-0028](0028-whatsapp-consent-and-eligibility.md)
Satisfies: the Development Specification's 🛑 Phase 5 gate item "retry/backoff limits"

## Context

The specification requires capped, backed-off retries ending in a visible failure log,
and that a down provider never blocks a sale. Grilling the proposal surfaced three
things the plain "retry N times" rule gets wrong:

- **The shop's own internet going down** is the most common failure, and it is not the
  message's fault. Counting it as an attempt turns one afternoon's outage into every
  message from that afternoon marked failed.
- **Money messages go stale.** "Rs 600 added, balance now Rs 9,750" delivered three days
  late — after the customer has paid — is wrong, not merely late.
- **Some errors break the whole account**, not one message: an expired or revoked key, a
  billing failure, a restricted account. Retried per message, one card problem becomes a
  wall of identical failures with the cause buried.

And one limit of the setting: Meta reports *delivery* and *read* status, and customer
replies, by calling a public web address. The shop PC has none (ADR-0001).

## Decision

### "Sent" means accepted
1. A message is **`sent` when Meta's API accepts it.** No webhooks, no relay, no tunnel in
   v1. The accepted cost: a message Meta accepted but could not deliver still shows as
   sent. **Trigger to revisit:** the client reports customers saying they never receive
   messages, or wants automatic "STOP" handling.

### Every send attempt ends in exactly one of five outcomes
2. The provider adapter classifies each attempt; the queue acts on the class, never on
   raw provider errors:

   | Class | Examples | What happens |
   |---|---|---|
   | **ok** | accepted | `sent`, `sent_at` recorded |
   | **no connection** | DNS failure, connection refused, timeout before a response | rescheduled; **does not use an attempt**; the age limit still applies |
   | **retryable** | provider 5xx, rate limited | uses an attempt; backoff |
   | **permanent (this message)** | not a WhatsApp number, malformed number, template rejected for this content | `abandoned` immediately, reason recorded |
   | **account broken** | invalid/expired/revoked key, billing failure, account restricted | **the whole queue pauses** (below); this message keeps its attempts |

   Unknown errors are treated as **retryable** — never silently as success, never as
   permanent.

### Retries and age limits
3. Backoff after a retryable failure: **1 min, 5 min, 30 min, 2 h, 6 h** — 5 attempts,
   then **`failed`**, visible on the Messages screen with the last error in plain words.
4. **Age limits, measured from when the message was queued, whatever the attempt count:**

   | Message | Give up after |
   |---|---|
   | Credit-sale notice | 48 hours |
   | Account notice | 7 days |
   | Monthly statement | 7 days |
   | Overdue reminder | 24 hours (the next sweep makes a fresh one) |

   Past its limit a message becomes **`abandoned`** ("too old to send") and is never sent.
5. **Every money message states "as of {date, time}"** in shop time (ADR-0024), so a
   message delayed within its age limit still tells the truth.
6. Eligibility is re-checked immediately before every attempt (ADR-0028 §5).

### Pausing when the account is broken
7. An **account broken** result sets a single paused state (a `setting` row: paused
   since, plain reason) and **stops all sending**. Queued messages wait; age limits keep
   running.
8. **Every screen shows an Admin a coral banner** while paused: *"WhatsApp messages are
   paused: {reason}. Nothing is lost; they'll send once this is fixed."* Cashiers do not
   see it (nothing they can act on).
9. **Resuming is automatic:** every 30 minutes the worker makes a check call that sends
   nothing and costs nothing — reading the sending number's details **(verify this
   endpoint is free and needs the same permissions as sending)**. On success, sending
   resumes; the banner clears. If a billing problem passes the check but the next real
   send fails the same way, it simply pauses again. An Admin can also press **Check now**.

### Never into the sale
10. Enqueueing happens after the sale commits and cannot raise into it (ADR-0003 §6); the
    worker runs on the scheduler, never inside a request. The DoD's hard gate — a sale
    completes with the provider down — is tested by making the fake provider fail in each
    class above.

## Alternatives Considered

- **A small online relay for delivery reports**, or **a tunnel exposing the shop PC**:
  real delivery status and inbound "STOP", at the cost of a second internet dependency, a
  hosting bill, and (for the tunnel) the shop PC on the internet, against ADR-0001.
  Rejected for v1, with the trigger above.
- **Attempts only, no age limit, connection failures counted.** Simpler. Lost: outages
  become mass failures, and stale balances can arrive days late.
- **One rule for all messages: retry for up to 7 days.** Loses fewer messages. Lost: a
  credit-sale balance arriving days out of date is worse than none.
- **Treat account-level errors like any failure.** Simplest. Lost: every message fails
  identically and nobody is told the real cause.
- **Pause but show it only on the Messages screen.** Quieter. Lost: an Admin who never
  opens that screen doesn't learn customers stopped getting updates.

## Consequences

- **Easier:** outages cost nothing; a broken card or key is one clear banner, not
  hundreds of failures; nothing stale or ineligible is ever sent.
- **Harder:** the adapter must classify Meta's errors correctly — the mapping from
  Meta's error codes to the five classes is built from Meta's documentation when the
  adapter is written and is the first thing checked in the real test send.
- **Honest gap:** "sent" can hide an undelivered message (point 1).

### Consequential test cases (all with the fake provider)
- A sale completes, and nothing is sent inline, with the provider failing in every class.
- No connection: rescheduled, `attempt_count` unchanged; still abandoned at its age limit.
- Retryable: backoff 1m/5m/30m/2h/6h, then `failed` after the 5th, with the error shown.
- Permanent: `abandoned` on the first attempt with the reason; no retries.
- Account broken: queue pauses, the message keeps its attempts, the Admin banner shows, a cashier sees none; a successful check resumes and clears it.
- Age limits per type, measured from queueing; an abandoned-as-too-old message is never sent.
- Unknown error class is retried, never marked sent.
- Money message text includes "as of" in shop time.
