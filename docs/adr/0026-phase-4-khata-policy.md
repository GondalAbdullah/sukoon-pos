# 0026 — Phase 4 Khata Policy: Permissions, Default Limit, Payments, Statements

Status: **Accepted** 2026-09-14 — the four questions answered by the client; the
smaller defaults below proposed alongside and recorded so they can be overturned
Date: 2026-09-14
Phase: 4
Depends on: [ADR-0008](0008-authentication-and-access-control.md) (permission codes, step-up), [ADR-0013](0013-customer-phone-identity.md), [ADR-0014](0014-credit-limit-enforcement.md), [ADR-0015](0015-credit-terms-and-overdue-tracking.md), [ADR-0016](0016-consolidated-data-model.md), [ADR-0024](0024-shop-timezone.md)

## Context

Phase 4 (Development Specification): customer CRUD with duplicate-phone handling,
ledger entries tied to sales and payments, full and partial payments, and a
per-customer statement view and export. Most of the policy was settled in the Phase 0
grill (ADR-0013 phone identity, ADR-0014 limits, ADR-0015 overdue). The permission
catalogue (`services/permissions.py`) deliberately left **recording a Khata payment**
and **exporting data** without codes "until they get their decision", and nothing
said what limit a newly opened Khata starts with — which matters because under
ADR-0014 a NULL limit means *unlimited*.

## Decision

### Asked and answered by the client (2026-09-14)

1. **Recording a payment: Cashier and Admin.** Customers pay whoever is at the
   counter. Every payment records who received it.
2. **A new Khata starts at a shop-wide default limit of Rs 10,000**, held in the
   setting `khata.default_credit_limit_paisa` (default `1000000`). An Admin can
   raise, lower, or remove (NULL = unlimited, ADR-0014) the limit per customer.
   A cashier therefore cannot open unlimited credit by omission.
3. **Payment methods: cash, bank transfer, JazzCash/Easypaisa, card** — stored as
   `cash | bank_transfer | mobile_wallet | card` in `payment.method` (no schema
   change). A free-text reference (bank reference, wallet transaction ID) is
   offered for the non-cash methods and optional: requiring it would block a real
   payment when the customer can't show the ID.
4. **Statements: a printable A4 PDF, produced by any staff.** Opening balance for
   the period, every entry with its running balance, closing balance.

### Proposed defaults, recorded here so they can be overturned

5. **Permission codes** (seeded by `flask seed`, dict-driven):

   | Code | Cashier | Admin | Step-up |
   |---|---|---|---|
   | `khata.view` — see customers, balances, history; print a statement | ✓ | ✓ | |
   | `customer.create` — open a Khata; edit name, phone, address, notes | ✓ | ✓ | |
   | `khata.record_payment` | ✓ | ✓ | |
   | `customer.manage_credit` — set limit and credit terms; archive/delete | | ✓ | |
   | `khata.override_limit` — authorise an over-limit credit sale (ADR-0014) | | ✓ | ✓ |

   Changing a limit is Admin-only but not step-up: raising a limit is a trust
   decision, not a destructive one (ADR-0008 §5 reserves step-up for destructive
   actions), and the override at the moment of sale is where step-up already lives.

6. **Over-limit override at the till (ADR-0014).** When a Cashier's credit sale
   would take the balance past the limit, the till blocks it and offers an Admin
   approval in place: the Admin's name and password, verified through
   `auth_service.authenticate` so wrong passwords count toward the normal lockout.
   ADR-0014 already accepts that an absent Admin means the sale can't be credit.
   If the signed-in user is an Admin, it's their own password (plain step-up).
   The ledger entry carries `override_authorised_by_user_id` and a note; the
   cashier stays on `sale.user_id`.

7. **Overpayment is accepted and shown as credit, never as a bare negative.**
   A payment larger than the balance asks for confirmation ("Rs 200 more than they
   owe — keep it as credit?"). `balance_paisa` may go below zero internally;
   everywhere a person reads it, a negative balance is written as
   **"In credit · Rs 200"** (the shop owes the customer). The credit is used up by
   their next credit purchase. Paying a credit *back out* in cash is a ledger
   adjustment, whose permission is still undecided — not built.

8. **Deleting a customer.** Blocked while the balance is anything but zero — owing
   *or* in credit (the spec names owing; a credit is equally money not settled).
   At zero, a customer with any history (a sale, a ledger entry, a payment) is
   **archived** (`is_active = 0`) — hidden from lists and the till picker, history
   intact — never hard-deleted. Only a customer with no history at all is deleted
   outright.

9. **Phone numbers (ADR-0013 as written).** Normalised on save; a duplicate
   normalised number asks "This number is already on X's Khata. Same person?" before
   saving. Opening a Khata asks the cashier to confirm the number in person
   (`shown` / `called`), or leave it unverified. Changing a verified number clears
   its verification.

10. **Ledger integrity.** Every balance change goes through one service function
    that writes the `credit_ledger_entry` and the `customer.balance_paisa` cache in
    the same transaction. `reconcile(customer)` recomputes the balance from the
    ledger; a test drives a scripted scenario and asserts the cache equals the
    ledger sum at every step (the Development Spec's "reconciles to zero" DoD).

11. **Overdue (ADR-0015)** is computed and badged in the Khata list and customer
    view. The reminder job and the "Send reminder" button are Phase 5 (WhatsApp).

## Alternatives Considered

The client-facing alternatives are recorded with the questions (see the session 23
changelog in context.md): Admin-only payments, no default limit, Admin-only Khata
opening, Admin-only statements, a CSV export alongside the PDF. For the proposed
defaults:

- **Step-up on every limit change.** Friction on a routine owner task, with no
  destructive outcome to protect; the risky moment (the over-limit sale) already has
  it.
- **Reject overpayments.** Loses real money-in or forces the cashier to hand change
  back for a Khata payment, and the spec explicitly asks for an explicit credit state.
- **Hard delete at zero balance.** Would orphan sales, payments and ledger rows, or
  cascade-delete financial history. Archiving keeps the books whole.

## Consequences

- **Easier:** the counter handles the whole Khata loop — open, sell, pay, print —
  without waiting for the owner, except for the one moment ADR-0014 said should wait.
- **Harder:** a negative balance is legal in the data, so every display path must
  use the shared formatter; a bare `|rupees` on `balance_paisa` is a bug.
- **Still undecided, deliberately:** ledger adjustments (correcting a mistaken
  payment or paying out a credit), and voiding a completed sale.

### Consequential test cases
- A new Khata gets the default limit from the setting; an Admin can change or remove it; a Cashier cannot.
- A Cashier can record a partial and a full payment; each writes a payment row, a ledger entry and the cached balance in one transaction.
- An overpayment leaves an explicit credit state, displayed as "In credit".
- A customer owing, or in credit, cannot be deleted; a settled customer with history is archived; one with no history is deleted.
- Over-limit: blocked for a Cashier; approved with a valid Admin name and password; a wrong password counts toward lockout; the entry records both people.
- The ledger reconciles to the cached balance at every step of a scripted sale/payment/refund scenario.
- A statement for a fixture scenario matches hand-calculated opening, rows, running balances and closing.
