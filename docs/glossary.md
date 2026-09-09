# Glossary — Domain Terms

Plain definitions for every domain-specific term used in the Sukoon codebase and
documentation. Per Operating Rule 14, a term is added here **the moment it is
introduced**, not retroactively.

Status key: **Settled** = agreed and in use. **Proposed** = drafted, awaiting the
Phase 0 grill-with-docs session.

---

## Business / shop-floor terms

**Khata** *(Settled)* — The running credit account a shop keeps for a trusted
customer: goods taken now, paid for later, tracked as a balance over time. Kept as
the Urdu term throughout the shipped UI by explicit design decision (Design System
2.4, 6). Never translated to "Credit Ledger" or similar in user-facing copy.

**Credit sale** *(Settled)* — A sale where no money changes hands at the till; the
invoice total is added to a customer's Khata balance instead.

**Credit limit** *(Proposed)* — A per-customer ceiling on outstanding balance.
Referenced by the design (a customer "near credit limit" is flagged coral) but not
present in the Development Specification's feature list. Needs a decision at grill:
does it block a sale, or only warn?

**Credit terms** *(Proposed)* — The agreed settlement window for a Khata customer
(the design mock shows "Credit terms: 30 days"). Currently display-only; whether it
drives any behaviour (overdue flags, statement timing) is undecided.

**Stock-in** *(Settled)* — Inventory arriving and being added to the counted stock
level, typically a supplier delivery. One of the three adjustment types.

**Stock-out** *(Settled)* — Inventory leaving outside of a sale: damage, expiry,
theft, or personal/shop use. One of the three adjustment types.

**Correct count** *(Settled)* — Setting a product's stock level to a physically
counted number, rather than adding or subtracting a delta. The third adjustment
type. Distinct from stock-in/stock-out because the recorded delta is derived, not
entered.

**Adjustment reason** *(Settled)* — The mandatory reason attached to every manual
stock change. This is the audit trail; no adjustment may be written without one.

**Low-stock threshold** *(Settled)* — The per-product quantity at or below which a
product is surfaced in the "needs attention" list and badged **Low** (amber).

**Out of stock / Restock** *(Settled)* — A product at zero stock. Badged **Restock**
(coral) — a genuinely urgent state, distinct from merely low.

**Walk-in customer** *(Settled)* — A sale with no customer record attached. The
default state of the Till. Only cash and card sales may be walk-in; a credit sale
requires a named Khata customer.

**Loose goods** *(Settled)* — Anything weighed out on a scale at the counter rather
than handed over as a sealed pack: atta, sugar, rice, daal, loose tea. Sold in
fractional amounts, so a customer can ask for 1.5 kg. Compare **sealed pack goods**.

**Sealed pack goods** *(Settled)* — Anything sold as a whole, countable item: tins,
bottles, cartons, whole sacks. Always a whole number of units. The prototype's
plus/minus stepper is designed for these.

**Milli-unit / thousandths** *(Settled)* — The unit every quantity is stored in. One
milli-unit is 1/1000 of the product's own unit, so 1.5 kg is stored as `1500` and 42
bags as `42000`. Columns carry a `_milli` suffix so the unit is impossible to
misread, exactly as `_paisa` does for money. Chosen so loose and packaged goods share
one integer quantity type with no floats anywhere. See ADR-0004.

**allows_fractional** *(Settled)* — A per-product flag controlling whether the till
offers decimal quantity entry. Presentation only: it never changes how the quantity
is stored. Off for sealed packs, on for loose goods.

**Entry by weight** *(Settled)* — Building a loose-goods sale line by typing the
weight read off the counter scale; the system computes the amount owed.

**Entry by amount** *(Settled)* — Building a loose-goods sale line by typing the
money the customer asked for ("Rs 200 worth of kidney beans"); the system computes
the weight to hand over. A normal way to buy here, not an edge case.

**Quantity source** *(Settled)* — A recorded note on every sale line of how its
quantity was captured: the stepper, a typed weight, a typed amount, or (reserved for
later) a connected scale. The audit trail for a disputed line. See ADR-0005.

**Weighed-label barcode** *(Proposed)* — A barcode printed by a scale that encodes
the weight or price inside its digits rather than identifying a product. Not
supported in v1; the scan handler is built as a resolver chain so support can be
added without touching the till. See ADR-0005.

**Rupee boundary** *(Settled)* — The rule that although money is stored in paisa,
every persisted amount is a whole number of rupees (a multiple of 100 paisa). Paisa
is the storage unit; the rupee is the transaction unit. See ADR-0007.

**Round at the line** *(Settled)* — Rounding a sale's money exactly once, on each
line total, then summing the rounded lines to get the subtotal. The opposite mistake
is leaving lines unrounded and rounding only the grand total, which prints a receipt
whose lines do not add up to its own total.

**Authoritative amount** *(Settled)* — On a line built by entry-by-amount, the money
the cashier typed is what is charged; the weight is derived from it and rounded. On
such lines, and only such lines, `line_total` deliberately does not equal
`quantity x unit_price`. Not a bug — see ADR-0007.

**Step-up authentication** *(Settled)* — Re-entering your password at the moment you
perform a destructive action, even though you are already logged in. Guards against
an unattended terminal left signed in as Admin. Authorises exactly one action. See
ADR-0008.

**Permission code** *(Settled)* — A named capability such as `sale.refund` or
`product.edit_price`, checked before an action runs. Authorisation is always tested
against a permission code, never against `role == 'admin'` written at a call site, so
adding a role later is a data change rather than a code change.

**Destructive action** *(Settled)* — Anything that rewrites history rather than adding
to it: a refund, a price edit, voiding a sale, adjusting a ledger entry. Admin-only
and step-up protected.

**Bulk entry** *(Settled)* — A screen built for one repeated motion: scan, type,
Enter, next. Used to populate the catalog quickly. The scanner drives navigation; the
cursor returns to the scan field after every committed row.

**Scan-as-you-go** *(Settled)* — Letting the catalog fill itself during real trading.
An unrecognised barcode at the till offers inline creation instead of blocking the
sale, so the shop can open before the catalog is complete.

**Provisional product** *(Settled)* — A product created at the till mid-sale, holding
only what the cashier could honestly know: name, selling price, and the barcode just
scanned. Cost, category, and threshold are left unset. Flagged, attributed, listed
under "Needs completing", and excluded from margin reporting so an unknown cost is
never reported as zero profit. **A product with no barcode is not provisional** — that
is a normal, complete product. See ADR-0011 and ADR-0012.

**Needs completing** *(Settled)* — The Stock filter listing provisional products, with
a count on the stat card. The list is meant to trend to zero; it is the visibility
that makes till-created products safe rather than silent debt.

**Normalised phone** *(Settled)* — A phone number reduced to one canonical form so
that `0300 5541298`, `03005541298` and `+923005541298` all match each other. Stored
alongside the number as the customer wrote it. Used for duplicate detection and for
notification delivery. See ADR-0013.

**Verified number** *(Settled)* — A customer phone number a member of staff has
confirmed belongs to the person in front of them, by having them show it on their own
phone or by ringing it. Until verified, a number may receive only a neutral notice
that an account was opened, never a balance or an amount. See ADR-0013.

**Overdue** *(Settled)* — A Khata customer with `balance_paisa > 0` whose reference
date is older than their `credit_terms_days`. Flagged in the Khata list and chased
with a WhatsApp reminder to a verified number. See ADR-0015.

**Reference date** *(Settled)* — The date an overdue check is measured from: a
customer's most recent `payment` ledger entry, or, if they have never made one, the
date of their first `credit_sale`. Only a genuine payment resets it — a refund or an
adjustment does not, since neither is the customer paying something. See ADR-0015.

**FIFO allocation** *(Superseded)* — Settling ledger payments against the oldest
outstanding purchase first, so each `credit_sale` entry ages individually. Considered
and rejected for overdue tracking in favour of account-level staleness, on
implementation weight: it would need a new settlement table. See ADR-0015.

**Credit limit override** *(Settled)* — An Admin, using step-up authentication,
authorising a credit sale that would take a customer's balance above their
`credit_limit_paisa`. Recorded on the ledger entry with the authorising Admin's
identity, distinct from the cashier who rang the sale. See ADR-0014.

**Statement** *(Settled)* — A per-customer summary of Khata activity over a period
(purchases, payments, closing balance), viewable, exportable, and sent monthly.

**Statement cycle** *(Proposed)* — The period a statement covers. Calendar month is
assumed; the exact boundary and its timezone is a grill question.

## Technical terms

**SKU** *(Settled)* — Stock Keeping Unit. The shop's own internal product code
(e.g. `OIL-5021`), assigned by the shop and unique across the catalog. Distinct
from a barcode.

**Barcode / QR code** *(Settled)* — The scannable code physically on the product.
Usually the manufacturer's EAN/UPC (e.g. `8964000109283`); generated by Sukoon only
for unlabelled goods. Unique across the catalog, enforced at the database level.

**Keyboard-wedge** *(Settled)* — How a USB barcode scanner presents itself to the
PC: as a keyboard that "types" the scanned digits very fast and then presses Enter.
No driver, no serial port. The practical consequence is that scanner input lands in
whatever field currently has focus, which is why the Till's scan field must hold
focus at all times.

**Invoice number** *(Settled)* — The human-facing, gap-free sequential identifier
printed on a receipt (e.g. `INV-2024-0413`). Must have no duplicates and no gaps
even under concurrent checkouts from two terminals.

**Paisa** *(Settled)* — 1/100 of a Pakistani Rupee. Every money value in the system
is stored as an integer number of paisa, never a float, per Operating Rule 8.
Columns carry a `_paisa` suffix so the unit is impossible to misread.

**WAL mode** *(Settled)* — Write-Ahead Logging, the SQLite journal mode this project
runs in. Lets one writer and several readers work at once instead of locking the
whole file, which is what makes two cashier terminals against one database file
practical.

**Soft delete** *(Settled)* — Marking a record inactive/archived rather than
removing it, so historical sales that reference it stay intact. Required for any
product with sales history.

**Notification queue** *(Settled)* — The table of pending WhatsApp messages. A
credit sale writes a row here and returns immediately; a background job does the
actual sending and retrying. This is the mechanism that keeps a slow or dead
provider from ever delaying a sale.

**Provider adapter** *(Settled)* — The thin interface the rest of the system uses to
send a WhatsApp message, so the actual vendor behind it can be swapped without
touching business logic.

**ESC/POS** *(Settled)* — The command language thermal receipt printers speak.
Talking it directly lets Sukoon print a receipt with no Windows print dialog. This
term is internal only; it must never appear in user-facing copy (Design System 6).

**PIN quick switch** *(Superseded)* — The login model the Design System mandated:
pick your name from a row of staff avatars, enter 4 digits, you are in. **Not built.**
Superseded by passwords for all users — see ADR-0008. The avatar row is kept; the
numeric keypad is replaced by a password field.

**Terminal** *(Settled)* — One PC or browser session acting as a till. Terminal 1 is
the server PC itself; others reach it over the shop LAN.

## Process terms

**grill-with-docs** *(Settled)* — The mandatory human-invoked interview that
pressure-tests a design before it is built, producing ADRs and glossary entries.
Cannot be triggered by the coding agent (`disable-model-invocation: true`).

**ADR** *(Settled)* — Architecture Decision Record. One numbered file per real
decision, recording context, the decision, rejected alternatives, and consequences.
Binding once Accepted.

**STOP AND ASK gate** *(Settled)* — A point in a phase where the agent must halt,
present the decision with a recommendation, and wait for recorded human approval.

**Definition of Done (DoD)** *(Settled)* — The explicit checklist a phase must pass
before the next begins. This project has two that both apply: the functional DoD
(Development Specification 11) and the design DoD (Design System 13).
