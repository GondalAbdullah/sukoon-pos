# 0030 — WhatsApp Message Content: Language, Detail, Replies, and Approved Wording

Status: **Accepted** 2026-09-14 — Phase 5 grill session; wording approved by the developer for the client
Date: 2026-09-14
Phase: 5
Amended by: [ADR-0032](0032-payment-receipt-message.md) (adds the payment receipt as a fifth message type)
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D2
Depends on: [ADR-0024](0024-shop-timezone.md) (shop time), [ADR-0026](0026-phase-4-khata-policy.md) §7 (balance wording), [ADR-0027](0027-whatsapp-provider-and-account.md), [ADR-0028](0028-whatsapp-consent-and-eligibility.md), [ADR-0029](0029-message-delivery-retry-and-pause.md)
Satisfies: the Development Specification's 🛑 Phase 5 gate item "message template wording"
**Deviates from:** Development Specification §6.F "credit-sale notification: items…" — see Decision 2

## Context

WhatsApp business-initiated messages must use **pre-approved templates**: fixed wording
with numbered blanks, approved by Meta per language **(verify category and turnaround)**.
So the wording is not a detail to settle at build time; it is what gets submitted, and
changing it later means re-approval.

The grill surfaced three problems the proposal's drafts didn't handle:

- **Item names are typed by staff.** A product created mid-sale carries whatever the
  cashier typed (ADR-0011 §2), typos included, straight to a customer's phone.
- **Lock screens.** A general store sells things people don't want listed on a phone a
  family member can see — medicines, personal-care items.
- **Replies go nowhere.** Customers will answer ("I paid yesterday", "not my purchase",
  "stop"). The API-registered number has no inbox anyone can open **(verify)**, and v1
  has no way to receive replies (ADR-0029 §1). A dispute sent as a reply would vanish
  while the customer believed they had told the shop.

## Decision

1. **Language: English**, one language for every customer. No per-customer language
   column.
2. **A credit-sale notice shows the number of items, never their names.**
   **This deviates from the Development Specification's "items"**, deliberately and at
   the client's choice: no private items on a lock screen and no staff-typed names sent
   to customers. "N items" counts bill lines (1.5 kg of loose atta is one item; "1 item"
   when there is one).
3. **The monthly statement is a short summary with the existing A4 PDF attached**
   (`services/statements.py`), the same document staff print. The PDF lists invoice
   numbers and amounts, not item names.
4. **Every message says where to reply.** A new setting, `whatsapp.reply_to_number` —
   the shop's everyday number — is **required before WhatsApp sending can be switched
   on**; Sukoon refuses to enable sending without it.
5. **Balances are worded exactly as on screen** (ADR-0026 §7): "Rs 10,030 owed", "Rs 230
   in credit", "Settled" — one shared formatter, never a bare negative. Times are shop
   time (ADR-0024).
6. **The approved wording** — `{…}` is filled per message; no exclamation marks, no blame:

   **Credit sale**
   > Al-Rehman General Store: {4 items}, {Rs 1,770}, added to your Khata as of
   > {14 Sep 2026, 8:26 PM}. Previous balance: {Rs 8,260 owed}. New balance:
   > {Rs 10,030 owed}. This number can't read replies. For questions, contact the shop on
   > {0300 1234567}.

   **Account notice** (ticked, number not yet confirmed — ADR-0028)
   > An account has been opened in the name of {Haji Muhammad Usman} at Al-Rehman General
   > Store. If this is not you, please contact the shop on {0300 1234567}. This number
   > can't read replies.

   **Monthly statement** (PDF attached)
   > Your Khata statement for {September 2026} from Al-Rehman General Store is attached.
   > Closing balance: {Rs 9,750 owed}. This number can't read replies. For questions,
   > contact the shop on {0300 1234567}.

   **Overdue reminder**
   > A gentle reminder from Al-Rehman General Store: {Rs 9,750} is due on your Khata, as of
   > {14 Sep 2026}. If you have already paid, thank you, and please ignore this message.
   > This number can't read replies. For questions, contact the shop on {0300 1234567}.

7. **If Meta requires changes during approval, the changed wording comes back for
   sign-off** and this ADR is amended — the code does not quietly adopt Meta's edit.
8. The wording lives in **one module** mapping each message type to its Meta template
   name and the ordered list of values; the fake provider renders the same text so tests
   assert exactly what a customer would read.

## Alternatives Considered

- **Urdu script / Roman Urdu / two languages per customer.** Urdu is the most natural
  for many customers; Roman Urdu is how many people text. Lost to English at the client's
  choice; two languages would add a column and double every approval.
- **First three item names then "and N more"**, or **every item**: closest to the
  specification. Lost on privacy and on sending staff-typed text to customers.
- **Statement as text only**, or **closing balance only**: simpler and cheaper. Lost:
  "monthly statement delivery" in the specification means the statement, and the PDF
  already exists.
- **Say "can't read replies" only once**, or **build reply reading now**: the first is
  forgotten by the next dispute; the second reverses ADR-0029 §1 with a second internet
  dependency.
- **A softer overdue reminder with no amount.** Gentler on a shared phone. Lost: the
  client approved stating the amount.

## Consequences

- **Easier:** nothing private or mistyped reaches a customer; every message tells them
  how to reach a person.
- **Harder:** the shop name is fixed text inside approved templates — **if the shop is
  renamed, the templates must be re-approved** (the `shop.name` setting alone won't change
  them).
- **Harder:** sending can't be switched on until `whatsapp.reply_to_number` is set.
- **Recorded deviation:** the specification's item list is intentionally not sent.

### Consequential test cases
- Rendered text for each type matches the approved wording exactly, from the fake provider.
- "1 item" / "4 items" pluralisation; loose goods count as one item each.
- No product name appears in any credit-sale message, including till-created products.
- Balances render as owed / in credit / Settled; never "Rs -".
- "as of" times are shop time.
- Sending cannot be enabled without `whatsapp.reply_to_number`; every message includes it.
- The statement message carries the same PDF bytes the statement screen downloads.
