# 0031 — When Messages Are Queued: Triggers, Statements, Reminders, and the Manual Button

Status: **Accepted** 2026-09-14 — Phase 5 grill session
Date: 2026-09-14
Phase: 5
Amended by: [ADR-0032](0032-payment-receipt-message.md) (adds the payment receipt as a fifth message type)
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D7, §D8, §D9
Resolves: **O-20** (overdue reminder and monthly statement collision)
Amends: [ADR-0015](0015-credit-terms-and-overdue-tracking.md) (the sweep's cadence, previously a working assumption)
Depends on: [ADR-0001](0001-technology-stack.md) (APScheduler in-process), [ADR-0016](0016-consolidated-data-model.md) (UNIQUE `dedupe_key`), [ADR-0024](0024-shop-timezone.md), [ADR-0028](0028-whatsapp-consent-and-eligibility.md), [ADR-0029](0029-message-delivery-retry-and-pause.md)

## Context

Four kinds of message need a moment at which they are queued. Two of them are
scheduled, and the scheduler only runs **while Sukoon is running** — a shop PC is off at
night, sometimes for days over Eid — so a job pinned to one instant silently misses.
ADR-0015 assumed a "daily" overdue sweep without saying how often one customer may be
chased; a daily message is spam that gets the number reported. O-20 has been open since
Phase 0: an overdue customer due a statement the same week shouldn't get two
uncoordinated messages. And the Khata mock's **Send reminder** button could bypass any
limit the schedule sets.

## Decision

Every message is queued with a **dedupe key** — the UNIQUE column makes a second queueing
of the same event a harmless no-op, whoever or whatever tries. Eligibility (ADR-0028) is
checked when queueing and again before sending. All times are shop time.

| Message | Queued when | Dedupe key |
|---|---|---|
| **Credit-sale notice** | right after a credit sale commits (never inside it) | `credit_sale:{sale_id}` |
| **Account notice** | when a customer is saved ticked with an unconfirmed number | `account_notice:{customer_id}:{phone_normalised}` |
| **Monthly statement** | 09:00 on the 1st, for the previous month — plus catch-up | `statement:{customer_id}:{YYYY-MM}` |
| **Overdue reminder** | the daily check at 11:00, or an Admin's button | `overdue:{customer_id}:{YYYY-MM-DD}` |

### Monthly statements
1. At **09:00 on the 1st**, a statement is queued for each customer who is ticked and
   confirmed, and whose closing balance for the previous month is **not zero, or who had
   any activity** in it. A settled customer with a quiet month gets nothing.
2. **Catch-up on start-up:** if Sukoon wasn't running at 09:00 on the 1st, the first
   start afterwards queues the missed month — **only until 09:00 on the 8th**. The window
   is measured from the 1st, not from queueing: a PC off for the whole first week skips
   that month's statements rather than sending them late. The skip is logged, so the
   Messages screen can say so.

### Overdue reminders (closes O-20)
3. The check runs **daily at 11:00**. It queues a reminder for each overdue customer
   (ADR-0015), ticked and confirmed, **unless** that customer has a reminder **queued or
   sent in the last 7 days**, **or** a statement **sent in the last 3 days** — the statement
   already shows the balance.
4. **No catch-up for missed days.** If the PC was off, the next check simply runs; the
   weekly limit makes a missed day irrelevant.

### The Send reminder button
5. **Admin only** — a new permission code, `khata.send_reminder` (Admin), seeded like
   ADR-0026's.
6. **The same limits as the schedule.** When a reminder was queued or sent in the last 7
   days, or a statement sent in the last 3, the button is disabled and says when the last
   one went ("Reminded 3 days ago"). Two presses — or a press racing the 11:00 check —
   can't queue two, by the dedupe key.
7. The button shows only for a customer who is actually overdue, ticked and confirmed;
   otherwise the screen says why not (no tick, number not confirmed, not overdue).

## Alternatives Considered

- **No catch-up window for statements** (always send the missed month eventually).
  Nothing skipped. Lost: a "closing balance" arriving weeks late misleads a customer
  who has paid since.
- **Statements sent by hand only.** Nothing unattended. Lost: they go out only when
  someone remembers.
- **One reminder per overdue spell.** Gentlest. Lost: a customer who ignores it hears
  nothing more.
- **A reminder every 3 days.** Most effective at collecting. Lost: highest risk of spam
  reports, and the shop's regulars are its business.
- **No automatic reminders at all.** Would supersede ADR-0015's automatic reminder; lost
  to the weekly rule.
- **Any staff may press Send reminder**, or **the button ignores the limit.** Lost:
  the first spreads a debt-collection decision to every cashier; the second lets the one
  rule that prevents spam be bypassed by the person most likely to be frustrated.

## Consequences

- **Easier:** O-20 is closed by a rule, not by hoping jobs don't overlap; restarting,
  double-clicking or a second worker can never duplicate a message.
- **Harder:** the scheduler needs a small persisted record of which months' statements
  ran (for catch-up and for "skipped" reporting).
- **Accepted:** a PC switched off for the whole first week of a month means no WhatsApp
  statements that month; printed statements are unaffected.

### Consequential test cases
- A credit sale queues exactly one notice, after commit; a failing enqueue doesn't affect the sale.
- Saving a ticked, unconfirmed customer queues one account notice per number; confirming later queues nothing new.
- Statements at 09:00 on the 1st for the previous month, correct across the month and timezone boundary; settled-and-quiet customers skipped.
- Catch-up: start on the 5th queues the missed month; start on the 9th doesn't, and logs the skip.
- Running the statement job twice queues nothing new.
- Overdue check: skips a customer reminded 6 days ago, reminds one reminded 8 days ago, skips one sent a statement 2 days ago.
- Send reminder: Admin only; disabled within the limits with the last-sent time; a double press queues one.
