# 0028 — WhatsApp Consent and Who May Be Messaged

Status: **Accepted** 2026-09-14 — Phase 5 grill session
Date: 2026-09-14
Phase: 5
Amended by: [ADR-0032](0032-payment-receipt-message.md) (adds the payment receipt as a fifth message type)
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D6
Amends: [ADR-0013](0013-customer-phone-identity.md) §4 (narrows when the neutral notice is sent), [ADR-0016](0016-consolidated-data-model.md) (`customer` gains consent columns; `notification_queue.notification_type` gains a value)
Depends on: [ADR-0026](0026-phase-4-khata-policy.md) §9 (a changed number is unconfirmed again)

## Context

WhatsApp's business rules require a customer to have agreed to receive
business-initiated messages **(verify current wording)**. Nothing in Sukoon records
that agreement: a number given "for the Khata" is not agreement to WhatsApp messages.

Adding it is a migration on `customer`, so it is expensive to reverse and was grilled
first. It also collided with ADR-0013 §4, which sends a neutral notice ("an account was
opened in your name… if this is not you, contact us") to an **unconfirmed** number as the
way a cashier's typo surfaces — a message to someone who may never have agreed to
anything. And a message can wait in the queue for hours (internet down) while the
customer's situation changes underneath it.

## Decision

1. **A tick on the customer: "Send updates on WhatsApp".** On the open-a-Khata form and
   editable afterwards. **It starts unticked**, never pre-ticked. Anyone who may edit a
   customer's contact details (`customer.create`, ADR-0026 §5 — Cashier and Admin) may
   tick or untick it. A customer who says no keeps an ordinary Khata.
2. **Schema** (one migration, Phase 5):
   ```
   customer.whatsapp_opt_in            BOOLEAN  NOT NULL DEFAULT 0
   customer.whatsapp_opt_in_at         DATETIME NULL
   customer.whatsapp_opt_in_by_user_id INTEGER  FK -> user.id NULL
   ```
   Existing customers migrate as **not opted in** — agreement is never assumed
   retroactively.
3. **Who may receive what** — one pure function decides, `message_eligibility(customer,
   notification_type)`, returning allowed or the reason not:

   | Customer state | Allowed |
   |---|---|
   | Archived, no normalised number, or **not ticked** | nothing |
   | Ticked, number **unconfirmed** | the neutral **account notice** only, once per number |
   | Ticked, number **confirmed** | credit-sale notices, statements, overdue reminders |

   ADR-0013 §4 still holds — no money detail ever reaches an unconfirmed number — but the
   neutral notice now also needs the tick. With no tick nothing is sent, so there is
   nothing a wrong number could learn.
4. **`notification_type` gains `account_notice`.** No database constraint exists on this
   column (ADR-0016 listed "rejects a fourth value" as a test case; that test was never
   written — found in this session). Validation lives in the queue service and gets a
   real test.
5. **Eligibility is checked twice: when queued, and again immediately before sending.**
   If the customer has since been unticked, archived, had their number changed, or lost
   confirmation, the message becomes `abandoned` with the reason and is never sent.
6. **Changing a customer's number clears the tick**, exactly as it already clears
   confirmation (ADR-0026 §9). Agreement given for one number never carries to a number
   that may belong to someone else; the cashier re-ticks with the customer present.
7. **Opting out in v1 is done by the shop** (untick on request). Reading a customer's
   "STOP" reply needs Meta to call the shop PC, which it can't reach — see the delivery
   decision later in this grill.

## Alternatives Considered

- **Giving a number counts as agreement.** Simplest at the counter. Lost: a customer
  surprised by messages can report the number, and Meta may restrict it **(verify)**;
  and it quietly redefines what the customer agreed to when they gave a number.
- **Ask on WhatsApp first ("reply YES").** The most rigorous. Lost for v1: reading the
  reply needs inbound webhooks to a public address the shop PC doesn't have.
- **The neutral notice goes even without a tick.** Keeps ADR-0013's typo safety net for
  every customer. Lost: it messages people who didn't agree — the thing the tick exists
  to prevent — and without a tick no money message would ever be sent anyway.
- **Drop the neutral notice.** Lost: a mistyped number would never be discovered through
  messaging, and ADR-0013 §4 would be superseded rather than narrowed.
- **Send what was eligible when queued.** Lost: a balance could reach a number the shop
  had already corrected away from, or a customer who had just asked to stop.
- **Keep the tick when the number changes.** Less re-asking. Lost: it assumes the new
  number is the same person's.

## Consequences

- **Easier:** "why didn't this customer get a message?" always has a recorded answer —
  the abandoned reason, or no tick.
- **Harder:** the counter has one more question when opening a Khata; the worker does a
  customer read before every send.
- **Forecloses:** sending anything to a customer who hasn't ticked, including for
  debt collection. If the shop later wants reminders without consent, that is a new
  decision with the platform's rules checked first.

### Consequential test cases
- A new customer is not opted in; existing customers migrate as not opted in.
- Not ticked → nothing queued for any type, including the account notice.
- Ticked + unconfirmed → only `account_notice`, once per normalised number; a second
  number gets its own notice.
- Ticked + confirmed → credit sale, statement, overdue reminder allowed; account notice not needed.
- Untick, archive, number change, or lost confirmation between queue and send → `abandoned` with the reason, provider never called.
- Changing the number clears the tick and records nothing new until re-ticked.
- An unknown `notification_type` is refused by the queue service.
