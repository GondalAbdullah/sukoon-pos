# 0027 — WhatsApp Provider, Account Ownership, and Billing

Status: **Accepted** 2026-09-14 — Phase 5 grill session (answers from the developer, for the client)
Date: 2026-09-14
Phase: 5
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D1
Depends on: [ADR-0001](0001-technology-stack.md) (WhatsApp is the only internet dependency), [ADR-0003](0003-module-boundaries.md) (`services/notifications/providers/`)

## Context

Phase 5 needs a WhatsApp sending provider, and the Development Specification's
🛑 gate requires the vendor to be confirmed before implementation. Three routes were
on the table: Meta's WhatsApp Business Cloud API directly, a Business Solution
Provider (reseller) on top of it, or unofficial WhatsApp Web automation.

Two facts outside the code decide this more than any technical merit: **who owns the
account and number** (a number registered to one business account is painful — and on
some platforms impossible — to move to another owner once customers receive messages
from it; a developer-owned account holding a client's number is the classic handover
failure), and **whether the owner can pay Meta** (Meta bills a payment card, and many
Pakistani cards are blocked or capped for international online payments).

## Decision

1. **Provider: Meta WhatsApp Business Cloud API, called directly.** No reseller.
2. **The account belongs to the shop owner**, created in the shop's name. The developer
   is added with developer access that the owner can remove at handover. The developer
   never holds the account.
3. **A new SIM, bought for this purpose**, is the sending number — not the shop's
   everyday number, which the owner keeps using in the normal WhatsApp app.
4. **Billing: the owner's own card**, confirmed by the developer to work for
   international online payments.
5. The provider sits behind the adapter interface ADR-0003 already reserves
   (`services/notifications/providers/`), with a **fake provider** used by every test.
   No business logic imports the Meta adapter directly.

## Alternatives Considered

- **A Business Solution Provider (360dialog, Gupshup, Twilio, Infobip…).** Would have
  won if the owner couldn't pay Meta by card (some bill locally). Lost because the card
  works: a reseller adds a markup to every message and one more company whose terms can
  change. Remains a drop-in via the adapter if Meta onboarding fails.
- **Unofficial WhatsApp Web automation (whatsapp-web.js, Baileys…).** Rejected outright:
  against WhatsApp's terms, the number can be banned, and it depends on a logged-in phone
  session that expires silently — the "provider lying" failure the specification is
  written against.
- **The shop's existing number.** Rejected: a number registered to the API generally
  can't be used in the ordinary WhatsApp app at the same time **(verify)**, so the owner
  would lose their everyday WhatsApp.
- **The developer's Meta account "for now".** Rejected: the client's number and message
  history would live in the developer's account; "for now" becomes permanent.

## Consequences

- **Easier:** at handover there is nothing to transfer — the owner already owns
  everything; removing the developer's access is one click.
- **Harder, and owned by the client:** creating the Meta Business account, adding the
  card, registering the new number, and getting message templates approved. The build
  can proceed against the fake provider meanwhile; a real send waits for this.
- **Watch, not decided:** a prepaid SIM that is never used may be deactivated by the
  mobile network **(verify the operator's inactivity rule)**; if the number is lost, the
  API registration goes with it. Trigger: before go-live, confirm with the operator what
  keeps the SIM active.
- **Unverified facts carried into later decisions:** Meta's current per-message pricing
  for Pakistan, messaging limits for a new account, and business-verification
  requirements. Checked when the account is created, not assumed in code.
