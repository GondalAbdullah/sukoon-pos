# 0034 — Phase 6 Reporting Policy: Access, Estimated Profit, Periods, and What Counts

Status: **Accepted** 2026-09-15 — access and profit basis answered by the client; the rest proposed alongside and recorded so they can be overturned
Date: 2026-09-15
Phase: 6
Resolves: **O-10** (Insights date-range controls)
Depends on: [ADR-0007](0007-money-rounding.md), [ADR-0011](0011-catalog-onboarding.md) (unknown cost is never zero), [ADR-0016](0016-consolidated-data-model.md), [ADR-0020](0020-phase-3-refund-and-discount-policy.md), [ADR-0024](0024-shop-timezone.md), [ADR-0025](0025-stock-limits-at-the-till.md), [ADR-0026](0026-phase-4-khata-policy.md)

## Context

Phase 6 (Development Specification): sales, inventory, low-stock, outstanding-credit and
basic profit/loss reports; a dashboard of the most-used numbers; date-range filters and
CSV/PDF export. The Insights reference shows today's sales against the same weekday last
week, credit outstanding, **"Estimated profit"** with a margin, busiest hours, sales by
category, and today's sales, under Today / This week / This month controls.

Two things had no decision:

- **Who may see it.** No permission exists for reports.
- **How profit is computed.** `sale_item` snapshots name and price but **not cost**
  (ADR-0016). Profit can only be computed against *today's* cost prices. Recording cost at
  sale would change ADR-0016's schema, which the specification routes through a
  grill-with-docs session.

O-10 asked whether the date controls are in scope; the specification's own step 3
("date-range filters") answers it.

## Decision

### Asked and answered by the client
1. **Admin only.** Insights, every report and every export require a new permission,
   **`report.view`** (Admin). Cashiers see none of it; the till, stock and Khata are
   unchanged.
2. **Profit is estimated at today's cost prices and always labelled so.**
   - A line's estimated cost = `line_total_for_quantity(product.cost_price_paisa,
     quantity_milli)` — the same once-at-the-line rounding as sales (ADR-0007).
   - **Lines whose product has no cost price are left out of profit and margin entirely**
     (ADR-0011: an unknown cost is never zero). Every profit figure states its
     **coverage** — "covers Rs 142,000 of Rs 184,250 in sales (77%)" — so a margin computed
     over part of the sales can't pass for the whole.
   - Margin % = estimated profit ÷ covered sales.
   - The label says what it is: *"Estimated at today's cost prices."* Past periods move if
     cost prices change; that is the accepted cost of not changing the schema.

### Proposed defaults
3. **O-10 resolved:** presets **Today · This week · This month**, plus a **custom from–to**
   on the reports screen. Periods are shop-time calendar ranges, half-open [start, end)
   (ADR-0024). **A week runs Monday to Sunday.**
4. **Comparison** (the dashboard's "busier than" line): Today against the **same weekday
   last week, up to the same time of day**; This week / This month against the previous
   week / month up to the same point. A comparison against a period with no sales is shown
   as "nothing to compare with", never as a percentage change from zero.
5. **What counts as a sale:** every completed sale in the period by when it was rung,
   **all payment methods** — a Khata sale is a sale the day it happens; what's still owed is
   the separate credit figure.
6. **Refunds** are deducted in the period **they are approved** (money moves then,
   ADR-0020). Net sales = sales − approved refunds. For profit, a refunded line that was
   **restocked** returns its estimated cost; a **damaged, not restocked** line keeps its
   cost (the goods are gone) — so a damaged return lowers profit, as it should.
7. **Stock is point-in-time, not ranged:** the inventory and low-stock reports show *now*.
   Stock value is at cost; products without a cost price are listed as "value unknown"
   with a count, never valued at zero or at sell price. The low-stock report separates
   **low**, **out of stock**, and **never counted** (ADR-0025) — the last is not "out".
8. **Outstanding credit is point-in-time:** customers who owe, oldest-overdue first
   (ADR-0015), with the total; customers **in credit** are listed separately and not netted
   against what's owed.
9. **Categories** are each product's *current* category (not snapshotted); products with
   none appear as "No category".
10. **Exports:** each report as **CSV** (numbers as plain rupees, no "Rs", for a spreadsheet)
    and **PDF** (A4, the same rows and totals as the screen, via one shared report
    document — the pattern receipts and statements already use).
11. **Performance:** totals, category, product and profit figures are **SQL aggregates** —
    including the per-line cost rounding, done in integer SQL. **Time buckets** (sales by day,
    busiest hours) can't be: SQLite has no timezone conversion, so they read only each sale's
    timestamp and amount and bucket them in shop time in Python. *(An earlier draft of this
    ADR said nothing is loaded into Python; corrected before building.)* Verified against a
    seeded dataset of **10,000 sales**; an index is added only if a measurement shows it's
    needed (an index is a migration and would be recorded).
12. **Stock value uses the money rule.** Phase 2's stock-value tile floored `cost × quantity`
    to the paisa; reports and the tile both now use `line_total_for_quantity` (half-up, whole
    rupees, ADR-0007), so the Stock screen and the inventory report can't disagree.

## Alternatives Considered

- **Cashiers see sales but not profit / everyone sees everything** (offered). Lost: the
  client treats totals and margins as owner information.
- **Record cost at the moment of sale** (offered). Exact and stable history, but a change to
  ADR-0016 requiring a grill session, and exact only for sales after it. **Trigger to
  revisit:** the owner finds estimated profit misleading because cost prices changed, or
  asks for exact profit.
- **Zero-cost for unknown items.** Rejected by ADR-0011 — it reports false profit.
- **Refunds against the original sale's date.** Keeps a sale and its refund together, but
  rewrites a closed period's figures after the fact; the approval date matches when money
  actually moved.
- **Sunday-start weeks.** Lost to Monday, the common convention for business weeks in
  Pakistan and ISO weeks.

## Consequences

- **Easier:** no schema change; every figure is traceable to rows that exist today; profit
  can't overstate itself silently.
- **Harder:** "Estimated profit" for a past month can differ from what it showed at the
  time. The label and this ADR say so.
- **Forecloses nothing:** recording cost at sale can be added later without changing how
  reports read their inputs.

### Consequential test cases
- A cashier gets 403 on Insights, reports and exports; an Admin gets 200.
- Estimated profit for a hand-built period equals sales − Σ(today's cost × quantity), with unknown-cost lines excluded and coverage stated.
- A restocked refund returns its cost; a damaged refund doesn't; refunds count in the approval period.
- Today / week (Monday start) / month boundaries in shop time; a sale at 00:30 Pakistan time on Monday belongs to the new week.
- An empty range renders cleanly and exports header-only CSV and a PDF saying there's nothing in the period.
- Comparison with an empty previous period reads "nothing to compare with".
- Stock value excludes and counts unknown-cost products; low-stock separates low / out / never counted.
- Credit lists owed customers oldest-overdue first and in-credit customers separately.
- CSV and PDF totals equal the on-screen totals.
- 10,000 seeded sales: each report computes within a stated time budget.
