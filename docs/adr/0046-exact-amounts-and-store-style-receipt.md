# 0046 — Exact Amounts Everywhere, and a Store-Style Receipt

Status: **Accepted**
Date: 2026-10-29
Phase: post-release (1.2.0)
Depends on: [ADR-0014](0014-credit-limit-enforcement.md), [ADR-0026](0026-phase-4-khata-policy.md), [ADR-0030](0030-whatsapp-message-content.md), [ADR-0039](0039-receipt-printing-on-windows.md)
Supersedes: [ADR-0045](0045-round-the-bill-not-the-line.md) (the bill rounded once, at its total)
Amends: [ADR-0007](0007-money-rounding.md) (the whole-rupee invariant on totals, payments and the Khata), [ADR-0044](0044-paisa-in-product-prices.md) §2

## Context

ADR-0045 (2026-10-28) kept what is paid in whole rupees by rounding the bill's total and
printing a Rounding line. On seeing it the client asked for **no Rounding line and the exact
total** on the bill, and for a receipt laid out like the big stores' (Imtiaz, Al-Fatah).

Offered the consequences — an exact total means paisa in the change, on card, and in the Khata
— the developer chose on 2026-10-29: **exact everywhere**.

## Decision

### 1. No rounding of money anywhere

Line totals, the bill's total, cash tendered, change, card amounts, Khata entries and balances,
refunds and Khata payments are all exact paisa. 3 × Rs 150.50 + Rs 110 is a bill of **Rs 561.50**;
paid with Rs 600, the change is **Rs 38.50**. The cashier settles the paisa by hand.

What still rounds, and only to the paisa or as an estimate: a weighed line's fraction of a paisa
(half-up, ADR-0046 keeps ADR-0045 §1), a by-amount line's derived weight (ADR-0005), and the cost
figures in reports (ADR-0034's estimate).

What stays whole rupees: a **by-amount** line (the customer names a rupee amount) and a Khata's
**credit limit** (it is a cap, not money owed).

### 2. Refunds

A refund returns exactly its lines, never more than the sale has left; the refund that takes the
rest returns exactly what was paid minus earlier refunds (ADR-0045 §3's cap, without the
rounding).

### 3. The receipt (client's request, 2026-10-29)

- Date as **28-Oct-2026** with a 12-hour time (07:30 PM); month names fixed in English.
- **No cashier name, no till name.**
- An **item table**: ITEM · QTY · RATE · AMOUNT, item names in **capitals**; a name too long for
  its column gets a line of its own above its figures. On 58 mm paper (32 characters) there is no
  room for columns, so figures go below each name as `qty x rate`.
- Items and total quantity, **NET AMOUNT** in bold (double height on the printer), how it was paid,
  cash and change.
- At the bottom: a thank-you line and the **shop's name, address and phone**, centred.
- The shop name also stays large at the top.

The address and phone are entered under **Settings → Shop details** (new). The old free-text
`shop.contact` setting, which no screen ever set, is read as the address when none is entered.
Khata statements print the same address and phone.

## Alternatives Considered

- **Exact bill, rounded only when paying** — rejected: the printed total and the money taken
  would differ.
- **Keep ADR-0045 and hide the Rounding line** — rejected: the lines would not add up to the total.

## Consequences

**Harder:** the cashier hands back change with paisa they cannot physically give, and settles it
by hand (the usual practice in shops that print exact totals). Khata balances and statements can
show paisa.

**No migration:** money was always stored in paisa; only the rules and the display change.

## Consequential test cases

- A bill of Rs 561.50 is charged Rs 561.50; change from Rs 600 is Rs 38.50
- A Khata credit sale and a Khata payment can carry paisa; the limit stays whole rupees
- Refunds sum to exactly what was paid
- The receipt has the date as 28-Oct-2026, no cashier or till, items in capitals in a table,
  NET AMOUNT, and the shop's name, address and phone at the bottom
- Settings → Shop details saves the name, address and phone; a blank name is refused
