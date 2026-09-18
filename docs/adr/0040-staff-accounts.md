# 0040 — Staff Accounts: Who Adds Them, and What Cannot Be Undone

Status: **Accepted** 2026-09-18 — built the day before go-live, after the developer found the gap
Date: 2026-09-18
Phase: 7
Depends on: [ADR-0008](0008-authentication-and-access.md), [ADR-0016](0016-consolidated-data-model.md), [ADR-0017](0017-phase-1-auth-details.md), [ADR-0038](0038-packaging-installation-and-delivery.md) §6

## Context

Sukoon could create exactly **one** account: the owner's, on the first-run setup screen (ADR-0038
§6). Every other account came from `flask seed`, a developer command with passwords in environment
variables. A shop with cashiers therefore had **no way to let them sign in at all** — found by the
developer testing the packaged application as an Admin, one day before go-live.

The gap existed because ADR-0008 settled *authentication* (passwords, roles, step-up) and ADR-0017
settled the *catalogue of permissions*, but nothing ever asked **who creates the accounts** once
Sukoon is a program the shop owns rather than a project a developer runs.

## Decision

1. **A new permission, `staff.manage`** (Admin), plus `settings.manage` for the Settings screen it
   lives behind. Both seeded automatically, so existing installs gain them on the next start.
2. **`staff.manage` is a step-up permission** (ADR-0008 §5): adding an account, resetting a
   password, changing a role or switching someone off asks the Admin for **their own password
   again**. An account is a key to the shop's money, and a till is often left signed in.
3. **Accounts are deactivated, never deleted.** A user is referenced by every sale, stock movement,
   refund and Khata entry they touched (ADR-0016). Deleting one would orphan that history, so
   "someone left" means `is_active = false`.
4. **The last active Admin cannot be switched off or demoted.** Otherwise a shop can lock itself out
   of prices, refunds, Insights, staff and settings, with no way back in from inside Sukoon.
5. **Names and initials must be distinct**, because sign-in accepts either (ADR-0017). A second
   "Nadia Bibi" is refused; a second person whose initials would collide gets `NB2`.
6. **Resetting a password also clears a lockout** (ADR-0017's five attempts / fifteen minutes): the
   Admin standing next to a locked-out cashier should not have to wait out the clock.

## Alternatives Considered

- **Let the owner delete staff.** Simpler to explain, and wrong: the history would lose the person
  who rang each sale, which is what makes the audit trail worth keeping.
- **No step-up for staff changes.** One less password prompt for the owner; lost because a till left
  signed in as an Admin would let anyone mint an account.
- **Allow demoting the last Admin, with a warning.** Rejected: a warning is not a guarantee, and the
  failure is unrecoverable from inside the product.
- **A "forgot password" flow.** Not built: it needs either email or a recovery secret, neither of
  which this shop has. **Consequence, recorded:** if a shop has one Admin and they forget their
  password, nobody can get in — the install checklist therefore requires **two** Admin accounts.
  **Trigger to revisit:** the first time a shop is locked out.

## Consequences

- **Easier:** a shop can hire, sack and rotate staff without the developer.
- **Harder:** the developer must now explain roles to the owner (the owner's guide does).
- **Accepted risk:** no self-service password recovery. Two Admins is the mitigation, and a database
  edit by the developer is the last resort.

### Consequential test cases
- A cashier gets 403 on every staff route and creates nobody.
- Adding someone without the Admin's own password is refused; with it, they can sign in and see a cashier's screens but not an Admin's.
- The last Admin cannot be switched off or demoted; with a second Admin, both become possible.
- Deactivating someone stops their sign-in and keeps their user row.
- A password reset clears `failed_login_attempts` and `locked_until`.
- Two people whose initials collide end up distinct (`NB`, `NB2`).
