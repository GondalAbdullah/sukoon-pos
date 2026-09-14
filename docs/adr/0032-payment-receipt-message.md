# 0032 — Payment Receipt Message (a Deliberate Scope Addition)

Status: **Accepted** 2026-09-14 — Phase 5 grill session; wording approved by the developer for the client
Date: 2026-09-14
Phase: 5
**Adds to the Development Specification's scope** (§6.F lists credit-sale notices and monthly statements; ADR-0015 added overdue reminders)
Amends: [ADR-0028](0028-whatsapp-consent-and-eligibility.md), [ADR-0029](0029-message-delivery-retry-and-pause.md), [ADR-0030](0030-whatsapp-message-content.md), [ADR-0031](0031-message-scheduling-and-cadence.md)

## Context

The grill asked a scope question the proposal hadn't: the specification never mentions
messaging a customer when they **pay**. Without a receipt, the last WhatsApp message a
customer holds after paying Rs 5,000 still shows the old, higher balance until next
month's statement — and "I paid, where's my proof?" is exactly the dispute a Khata
system exists to prevent. Refunds were considered too.

## Decision

1. **A fifth message type, `payment_receipt`**, queued right after a Khata payment
   commits (`khata_service.record_payment`), never inside it.
2. **Eligibility** (ADR-0028): like the money messages — ticked **and** confirmed.
3. **Dedupe key** (ADR-0031): `payment:{payment_id}`.
4. **Age limit** (ADR-0029): **48 hours**, like a credit-sale notice — a receipt showing
   a stale balance days later is worse than none.
5. **Approved wording** (ADR-0030 conventions: English, shop time, shared balance words,
   the reply-to line; no typed payment reference — it is staff-typed text, the same reason
   item names were excluded):

   > Al-Rehman General Store: payment of {Rs 5,000} received on your Khata as of
   > {14 Sep 2026, 8:26 PM}. New balance: {Rs 4,750 owed}. This number can't read
   > replies. For questions, contact the shop on {0300 1234567}.

   An overpayment reads "New balance: {Rs 250 in credit}".
6. **Refunds send nothing.** A credit refund is rare and the customer is at the counter
   when it's approved; the next statement shows it.

## Alternatives Considered

- **Receipts and refund messages both.** Every balance change messaged. Lost: one more
  template and bill for a rare event with the customer already present.
- **Keep to the specification's messages.** Smallest build and bill. Lost: the one
  message that settles "did my payment count?" would be missing.
- **Include the payment method** ("by JazzCash / Easypaisa"). Offered; not chosen.

## Consequences

- **Recorded as scope added**, not discovered in code: Phase 5's DoD and tests cover five
  message types, not three.
- One more template to get approved before go-live.

### Consequential test cases
- Recording a payment queues one receipt after commit; a failing enqueue doesn't undo the payment.
- Not queued for a customer who isn't ticked and confirmed; re-checked before sending.
- Rendered text matches the approved wording; an overpayment shows "in credit"; no reference text appears.
- Abandoned after 48 hours unsent.
