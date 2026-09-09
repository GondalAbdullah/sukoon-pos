# 0013 — Customer Phone Identity and Verification

Status: **Accepted**
Date: 2026-09-09
Phase: 0 (grill-with-docs session 1)
Resolves: O-4
Scope note: phone verification is a **client-added requirement**, present in neither
governing document. Recorded here under Operating Rule 13 rather than absorbed
silently. Affects Phase 4 and Phase 5.

## Context

The edge-case matrix says duplicate customers sharing a phone number are "prevented
or flagged" — two opposite designs, one of which had to be chosen before the
migration froze the constraint.

A hard unique constraint breaks a normal situation: two brothers, or a father and
son, each running a Khata on the household's single phone. Blocked from saving, a
cashier types a fake number or leaves it blank, and the data is worse than the
duplicate would have been.

But the phone number is also where WhatsApp balance notifications are sent. Two
accounts on one number means one person receives another's balance, and a number
given wrongly — by mistake or deliberately, to send debt notices elsewhere — means
financial detail goes to a stranger while the real customer sees nothing and later
disputes the debt.

Confirmed with the client on 2026-09-09: **different customers may share a phone
number**, and a customer opening a Khata should confirm the number is genuinely
theirs.

## Decision

### 1. Flag duplicates, do not constrain them

No unique constraint on `customer.phone`. Saving a customer whose normalised number
already exists shows a confirmation first:

> This number is already on Haji Muhammad Usman's Khata. Same person?

The cashier confirms deliberately, and the duplicate is then permitted. Detection
happens on the **normalised** number, not the typed string.

### 2. Numbers are normalised on save

The same number is written many ways, and stored as typed, none of these match:

```
0300 5541298    03005541298    +92 300 5541298    +923005541298
```

`normalise_phone(raw) -> canonical | None` is a pure function in `services/`,
exhaustively boundary-tested. It strips spaces, dashes and brackets and resolves the
`+92` / `0092` / leading-`0` prefixes to one canonical form. Both forms are stored:
`phone_normalised` for matching and delivery, `phone_raw` for display, so the
customer's own way of writing it survives.

An unparseable number is **not** silently coerced. It is rejected at input with a
plain message, or stored with `phone_normalised = NULL`, which excludes it from
matching and from notification delivery. Guessing at a malformed number would send a
stranger someone's balance.

### 3. A number carries a verification state

```sql
phone_verified          BOOLEAN  NOT NULL DEFAULT 0
phone_verified_at       DATETIME NULL
phone_verified_method   TEXT     NULL   -- 'shown' | 'called' | 'otp'
phone_verified_by_user_id INTEGER FK NULL
```

**In v1, verification happens in person.** When a Khata account is opened, the till
prompts the cashier to confirm the number belongs to the person in front of them —
by having them show it on their own phone, or by ringing it and hearing it ring. The
cashier records which. It is not cryptographic proof, but face to face at a counter
it is strong, and it costs nothing and needs no internet.

### 4. No financial detail goes to an unverified number

This is the rule that makes an unverified number safe rather than merely marked.

- **Unverified:** only a neutral notice may be sent — *"An account has been opened in
  the name of X at Al-Rehman General Store. If this is not you, please contact us."*
  **No balances, no amounts, no items.** A wrong number learns nothing financial, and
  the message itself is how the mistake surfaces.
- **Verified:** full notifications as designed.

An unverified number never blocks a sale, never blocks opening a Khata, and never
blocks recording a payment. It only limits what may be sent to it.

The Khata list shows an unverified-number badge, so the owner can see and clear them.

### 5. OTP verification is deferred, with a trigger

Sending a one-time code over WhatsApp and having the customer read it back is the
rigorous method, and `phone_verified_method = 'otp'` is reserved for it.

**Not built in v1.** It requires internet at the moment a Khata is opened, which the
offline-first guarantee otherwise avoids, it costs a provider message per attempt,
and the WhatsApp adapter does not exist until Phase 5.

**Trigger:** Phase 5 completing, plus the client wanting stronger proof than
in-person confirmation. At that point it is a small feature — generate a code, queue
one message, compare locally — because the seam and the state field already exist.
Tracked as O-18.

## Alternatives Considered

- **A unique constraint on phone** — rejected. It breaks the household-phone case and
  drives cashiers to enter fake numbers, degrading exactly the data it means to
  protect.
- **Matching duplicates on the raw typed string** — rejected. Four spellings of one
  number all miss each other, so the check would almost never fire.
- **Blocking notifications entirely until verified** — rejected. The neutral opening
  notice is often *how* a wrong number is discovered; silence would hide the mistake.
- **Sending full balances to unverified numbers** — rejected. It is precisely the leak
  this decision exists to prevent.
- **OTP in v1** — rejected on offline dependency, provider cost, and Phase 5 ordering.
  Deferred with a real trigger rather than dropped.
- **Requiring a phone number at all** — rejected. Some Khata customers will not have
  one; the column stays nullable and such an account simply receives no notifications.

## Consequences

**Easier:** households sharing a phone work naturally. Duplicate detection actually
fires, because it compares canonical forms. No financial information can reach an
unverified number, which closes the leak without blocking any counter workflow.

**Harder:** two phone columns instead of one, and every send path must check
`phone_verified` before choosing a message template. That check has to be enforced in
the notification service, not remembered at each call site.

**Forecloses:** nothing. OTP slots into the reserved method value.

## Consequential test cases

- All four spellings of one number normalise to the same canonical form
- An unparseable number is rejected or stored with a null normalised form, never guessed
- Saving a customer with an existing normalised number prompts for confirmation
- Two customers may share a number once confirmed
- An unverified number receives the neutral notice and never an amount
- A verified number receives full notifications
- A customer with no phone number can still hold a Khata and be sold to
- Verification records who confirmed it, when, and by which method
