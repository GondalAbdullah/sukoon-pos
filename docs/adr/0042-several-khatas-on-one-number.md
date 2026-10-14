# 0042 — Several Khatas on One Phone Number

Status: **Accepted** 2026-10-13 — the five questions below answered in session 36
Date: 2026-10-13
Phase: 8 (before go-live)
Amends: [ADR-0013](0013-customer-phone-identity.md) §1 and §3, [ADR-0030](0030-whatsapp-message-content.md) §6
Depends on: [ADR-0014](0014-credit-limit-enforcement.md), [ADR-0026](0026-phase-4-khata-policy.md), [ADR-0028](0028-whatsapp-consent-and-eligibility.md), [ADR-0031](0031-message-scheduling-and-cadence.md)

## Context

A customer wants to keep his finances apart: Ali keeps one Khata for home groceries,
one for his office, and one he runs on behalf of his brother — all on **his own phone
number**.

ADR-0013 already allows a number to be on more than one Khata (no unique constraint),
but it was written for *different people* sharing a household phone. For one person
holding several Khatas it gets in the way:

- The duplicate warning asks "Same person?" and tells the cashier *"If it's the same
  person, use the existing Khata instead"* — the opposite of what Ali wants.
- Three Khatas called "Ali Raza" can't be told apart at the till, so a sale can land on
  the wrong one.
- Each Khata is confirmed separately, so Ali would show his phone three times.
- **None of the approved WhatsApp messages say which Khata they are about.** Three
  "New balance: …" messages with different figures arriving on one phone look like
  mistakes.

## Decision

1. **A Khata has an optional label.** A new column `customer.label` (up to 40
   characters) — "Home", "Office", "Brother – Bilal". Wherever a Khata is named, on
   screen, on the receipt, statement and in every WhatsApp message, it reads
   **"Ali Raza (Home)"**; with no label, just "Ali Raza". One property,
   `Customer.display_name`, produces it. The till and Khata search match the label too.

2. **Two active Khatas on one number may not share the same name *and* label**
   (compared without case or surrounding spaces). Opening a second "Ali Raza" with no
   label on Ali's number is refused with a message asking for a label. Enforced in the
   service, not the database: a number-less Khata, or Khatas on different numbers, may
   share a name exactly as before.

3. **Opening another Khata on a known number is a normal choice, not a suspicion.** The
   warning now reads *"This number already has a Khata: Ali Raza (Home). Open another
   Khata on it?"*, explains that one person can keep separate Khatas (home, office,
   someone they pay for), and offers "Go to …" or "Open another Khata on this number".
   It still has to be confirmed deliberately (ADR-0013 §1 stands).

4. **Each Khata keeps its own credit limit, terms, balance and overdue clock.** A new
   Khata on a known number starts at the shop default (ADR-0026 §2) like any other. Ali
   with three Khatas can therefore owe up to three default limits; an Admin who wants
   less lowers them per Khata. No combined limit (ADR-0014 unchanged).

5. **A number already confirmed on another active Khata carries over, recorded.** When
   a Khata is opened on — or edited to — a number that is confirmed on another active
   Khata, and the cashier didn't confirm it themselves, it is marked confirmed with
   `phone_verified_method = 'same_number'`, `phone_verified_from_customer_id` pointing
   at the Khata it came from, and the opening staff member and time. Shown as "already
   confirmed on Ali Raza (Home)". A method the cashier picked themselves (shown /
   called) always wins.

   **WhatsApp agreement does not carry over** (ADR-0028 §1): it is given per Khata, and
   stays a tick the cashier sets for each one.

6. **A Khata opened on someone else's number is not treated differently.** Ali's
   brother's Khata on Ali's number sends its messages to Ali — that is the point. Already
   accepted by ADR-0013.

7. **Every money message names the Khata** (amends ADR-0030 §6). One new blank,
   `{khata}`, filled with `display_name`:

   **Credit sale**
   > Al-Rehman General Store: {4 items}, {Rs 1,770}, added to the Khata of
   > {Ali Raza (Home)} as of {14 Sep 2026, 8:26 PM}. Previous balance: {Rs 8,260 owed}.
   > New balance: {Rs 10,030 owed}. This number can't read replies. For questions,
   > contact the shop on {0300 1234567}.

   **Payment received**
   > Al-Rehman General Store: payment of {Rs 5,000} received on the Khata of
   > {Ali Raza (Home)} as of {14 Sep 2026, 8:26 PM}. New balance: {Rs 250 in credit}.
   > This number can't read replies. For questions, contact the shop on {0300 1234567}.

   **Monthly statement** (PDF attached)
   > The Khata statement of {Ali Raza (Home)} for {September 2026} from Al-Rehman General
   > Store is attached. Closing balance: {Rs 9,750 owed}. This number can't read replies.
   > For questions, contact the shop on {0300 1234567}.

   **Overdue reminder**
   > A gentle reminder from Al-Rehman General Store: {Rs 9,750} is due on the Khata of
   > {Ali Raza (Home)}, as of {14 Sep 2026}. If you have already paid, thank you, and
   > please ignore this message. This number can't read replies. For questions, contact
   > the shop on {0300 1234567}.

   **Account notice:** wording unchanged; its `{name}` blank now carries `display_name`.

   The same wording is used for every customer, single Khata or not: one template set to
   submit. The templates have **not yet been submitted to Meta** (O-23 open), so this costs
   no re-approval. The statement PDF names the Khata the same way at its top.

## Alternatives Considered

- **Type the distinction into the name ("Ali (Home)").** No migration, but nothing stops
  two identical names on one number, and the label can't be searched or shown apart.
- **New Khatas on a used number start at no credit**, or **one combined limit per
  number.** More owner control over total exposure, but the owner chose per-Khata limits
  as they work today; a combined limit would rewrite ADR-0014 enforcement.
- **Confirm the number again for every Khata.** Strictly ADR-0013, but asks Ali to prove
  the same phone three times in one visit.
- **Flag Khatas held "on behalf of" someone.** Rejected: ADR-0013 already accepts a
  shared number, and the number owner receiving the messages is the intent.
- **Name the Khata only when a number has several.** Keeps today's wording for most
  customers, but doubles the templates to get approved.
- **Leave the message wording alone.** Ali couldn't tell which Khata a message is about.

## Consequences

- **Easier:** one person runs separate Khatas cleanly; the till shows which is which; a
  message always says which Khata it concerns.
- **Harder:** every place that names a customer must use `display_name`, not `name`.
  The four money templates gained a blank — what is submitted to Meta under O-23 is
  this ADR's wording, not ADR-0030's.
- **Forecloses:** nothing. A combined per-number limit could still be added later.

### Consequential test cases
- A Khata's display name is "Name (Label)", or just the name without a label.
- A second Khata on the same number with the same name and no label is refused; with a
  different label it opens.
- The same name and label on *different* numbers, or with no number, is allowed.
- A new Khata on a number confirmed elsewhere is confirmed as `same_number`, pointing at
  the source Khata; a cashier's own method wins; an unconfirmed source passes nothing.
- WhatsApp agreement is not carried over.
- Each Khata gets the default limit independently.
- Every money message names the Khata; the rendered text matches this ADR exactly.
- An older queued message without the new blank is filled from the customer at send time.
