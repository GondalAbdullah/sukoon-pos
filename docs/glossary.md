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

**Credit limit** *(Settled — ADR-0014, ADR-0026)* — A per-customer ceiling on what
they may owe. A credit sale that would take the balance past it is blocked for a
Cashier and needs an Admin's approval at the till. A new Khata starts at the shop
default, Rs 10,000 (`khata.default_credit_limit_paisa`); an Admin may change it or
remove it (no limit). "Near credit limit" in the list means 80% or more used.

**Credit terms** *(Settled — ADR-0015)* — The agreed settlement window in days. With
terms set, a Khata with a balance is flagged **overdue** once that many days pass
since their last payment (or their first credit purchase, if they've never paid).
Only a payment resets the clock. No terms means never flagged.

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

**Counted / never counted** *(Settled — ADR-0025)* — A product is *counted* once a
person has told Sukoon how many exist: at least one stock-in (a delivery) or a correct
count. Until then it is *never counted*, and its zero level means "unknown", not
"none". The till caps a counted product at its stock level; a never-counted product is
not capped.

**Found at the till** *(Settled — ADR-0025)* — A stock-in Sukoon books automatically at
checkout for a never-counted product, for exactly the quantity the sale needs, so the
sale can deduct it without the level going negative. Tagged `found_at_till` and named in
the stock history ("Found at the till — not yet counted (INV-…)"). It never makes a
product counted.

**Shop time** *(Settled — ADR-0024)* — The one timezone every displayed time is in —
screens, receipts, and the year on an invoice number — set by `shop.timezone`,
default Asia/Karachi. Times are still stored in UTC.

**Out of stock / Restock** *(Settled)* — A product at zero stock. Badged **Restock**
(coral) — a genuinely urgent state, distinct from merely low.

**Walk-in customer** *(Settled)* — A sale with no customer record attached. The
default state of the Till. Only cash and card sales may be walk-in; a credit sale
requires a named Khata customer.

**Cart** *(Settled)* — The in-progress sale on the Till, before payment. Held in the
signed session in v1 (one row per sealed product with a stepper quantity; a fresh
row per loose weigh-out). A cart is not "ready" for checkout while any loose line
still needs a weight. It does not survive session loss — see context.md §4b.

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

**Loose-goods cart row** *(Settled)* — The Till cart row for a product with
`allows_fractional = 1`. In place of the whole-number stepper it carries an
inline-expanding control: a two-segment *Weight (kg) / Amount (Rs)* toggle, one
input, and a live `≈` preview of whichever direction is not being typed. Collapses
to a compact value pill once entered. Designed 2026-09-11 (resolves O-11); see
context.md §4b, ADR-0004, ADR-0005.

**Needs weight** *(Settled)* — The amber state a loose-goods cart row sits in when it
has been added but no weight or amount has been entered yet (the cashier is still at
the scale). The row commits so scanning can continue, but checkout is blocked until
every loose line has a quantity. Amber, not coral — attention soon, not now.

**Invoice claim** *(Settled)* — Taking the next invoice number is a single atomic
`UPDATE … RETURNING` against the one `invoice_counter` row, so two terminals
checking out in the same second serialise on that row and can produce neither a
duplicate nor a gap. The claim is part of the sale's own transaction — if the sale
rolls back, the number is released. See ADR-0016, `sales_service.claim_invoice_number`.

**All-or-nothing sale** *(Settled)* — A sale, its line items, every line's stock
deduction, and (for a credit sale) its ledger entry commit in one transaction. A
failure anywhere — not enough stock, a bad line, a crash — rolls back the whole
thing: no partial sale, no half-deducted stock, no consumed invoice number.

**PDF fallback** *(Settled)* — When the thermal printer is missing, unconfigured, or
unreachable, the receipt is produced as an 80 mm PDF the cashier can download and
print from the browser instead. The sale is already committed by the time the
receipt is issued, so a dead printer never blocks a sale — it only changes the
medium. See `services/receipts/`, Development Spec §11 Phase 3.

**Auto-advance countdown** *(Settled)* — On the Sale Complete screen, a quiet
progress ring on "Start next sale" that advances to the next sale on its own after
~8 seconds; any key or tap cancels it. Follows the Design System (Figure 8); the
prototype's omission of it is not a decision (ADR-0006). Resolves O-9.

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

**Refund** *(Settled)* — Returning money (or credit) to a customer against an earlier
sale, reversing its stock and, for a credit sale, its ledger entry. Always tied to
the original invoice; may cover part of it. A **Cashier initiates** a refund and an
**Admin approves** it with step-up — nothing moves (no stock, no cash, no ledger
entry) until approval. See ADR-0020.

**Pending approval** *(Settled)* — The state a refund sits in after a Cashier
initiates it and before an Admin approves or rejects it. A `refund` row exists but
has had no effect on stock, the drawer, or the ledger.

**Restock flag** *(Settled)* — A per-line choice on a refund: ticked (the default),
the returned quantity goes back into sellable stock on approval; unticked, the goods
came back damaged and no stock movement is posted. See ADR-0020.

**Ledger reversal** *(Settled)* — How a refund against a credit (Khata) sale is paid:
a negative `credit_ledger_entry` of type `refund` that reduces the customer's
balance, instead of cash leaving the drawer. Does not reset the overdue clock
(ADR-0015).

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

**Invoice year rollover** *(Settled)* — The invoice sequence resets to 1 on the first
sale of a new calendar year, so numbers stay short (`INV-2024-0413`,
`INV-2025-0001`) and match the shop's paper-invoice-book convention. Reset happens
inside the same atomic claim that allocates the number, so two terminals racing on
the year's first sale still cannot collide. See ADR-0016 addendum.

**Consolidated schema** *(Settled)* — The single current-state data model document
(ADR-0016) that merges every amendment made to the original draft (ADR-0002) during
the grill session, so Phase 1 builds against one document instead of reading twelve.
ADR-0002 itself is kept, unedited, as the historical starting point.

**Statement** *(Settled)* — A per-customer summary of Khata activity over a period
(purchases, payments, closing balance), viewable, exportable, and sent monthly.

**Net sales** *(Settled — ADR-0034)* — Everything sold in a period, by every payment
method (Khata included), minus refunds approved in that period.

**Estimated profit** *(Settled — ADR-0034)* — Net sales minus what those items cost *at
today's cost prices*. Items without a cost price are left out entirely rather than counted as
free, so it always comes with its **coverage** — the share of sales it could be worked out
for. A past period's figure changes if a cost price changes.

**Coverage** *(Settled — ADR-0034)* — How much of a period's sales estimated profit is based
on, e.g. "covers 93% of sales"; the rest were items with no cost price.

**Statement cycle** *(Settled — ADR-0024, ADR-0026)* — A calendar month on the
shop's clock (Pakistan time), or "all time". A purchase at 01:00 on the 1st belongs
to the new month even though it is still the previous day in UTC.

**In credit** *(Settled — ADR-0026)* — A Khata whose customer has paid more than they
owed: the shop owes them. Stored as a negative balance, but always shown as
"Rs 200 in credit", never "Rs -200". Used up by their next credit purchase.

**Opening / closing balance** *(Settled)* — On a statement, what the customer owed (or
was in credit) at the start and end of the period. Opening + purchases − payments −
refunds = closing.

**Confirmed number** *(Settled — ADR-0013)* — A customer phone number the cashier
checked in person — the customer showed it on their phone, or the cashier rang it.
An unconfirmed number never receives anything about money (Phase 5).

**WhatsApp consent (the tick)** *(Settled — ADR-0028)* — "Send updates on WhatsApp",
ticked on a customer when they agree to messages. Starts unticked. Without it Sukoon
sends that customer nothing at all. Changing their number clears it.

**Account notice** *(Settled — ADR-0013, ADR-0028)* — The one neutral message a ticked
customer with an **unconfirmed** number may receive: an account was opened in their name
at the shop, contact us if this isn't you. No amounts, ever. Sent once per number.

**Message eligibility** *(Settled — ADR-0028)* — Whether a customer may receive a given
kind of message right now, decided from their tick, number, confirmation and whether the
Khata is archived. Checked when a message is queued and again just before it is sent.

**Abandoned message** *(Settled — ADR-0016, ADR-0028)* — A queued message Sukoon gave up
on for good, with the reason recorded (for example, the customer was unticked before it
went out). Different from **failed**, which means sending kept not working.

**Sent (message)** *(Settled — ADR-0029)* — WhatsApp's API accepted the message. It does
not prove the customer's phone received it; Sukoon has no delivery reports in v1.

**Failed message** *(Settled — ADR-0029)* — A message that kept hitting errors worth
retrying and used all five attempts. Shown to the Admin with the last error; can be
retried by hand.

**Age limit** *(Settled — ADR-0029)* — How old a queued message may get before Sukoon
gives up on it, so a balance never arrives days out of date: 48 hours for a credit-sale
notice, 24 hours for an overdue reminder, 7 days for statements and account notices.

**Paused sending** *(Settled — ADR-0029)* — The state when the WhatsApp account itself
can't send (expired key, card declined, account restricted). All messages wait, an Admin
sees a banner, and sending resumes by itself once a check succeeds.

**Message template** *(Settled — ADR-0030)* — The fixed wording of a WhatsApp message,
with blanks for the customer's details, that Meta must approve before it can be sent.
Changing the wording, or the shop's name inside it, means approving it again.

**Reply-to number** *(Settled — ADR-0030)* — The shop's everyday phone number, printed in
every WhatsApp message, because the number that sends the messages can't read replies.
Sending can't be switched on until it is set.

**Dedupe key** *(Settled — ADR-0016, ADR-0031)* — A label that names one message event,
such as "the statement for customer 12, September 2026". The database accepts each label
only once, so a restart, a double click or a second worker can never send the same
message twice.

**Statement catch-up** *(Settled — ADR-0031)* — If Sukoon was switched off at 9 am on the
1st, it queues last month's WhatsApp statements when it next starts, but only until 9 am
on the 8th. After that the month is skipped rather than sent late.

**Daily cap** *(Settled — ADR-0033)* — The most WhatsApp messages Sukoon will send in one
day (default 200). Reaching it pauses sending until the next day, so a bug can never run
up the owner's bill.

**Sending switched off** *(Settled — ADR-0033)* — WhatsApp is turned off in Sukoon:
nothing is queued at all. Not the same as **paused**, where messages keep waiting because
the shop means to be sending.

**Outcome unknown** *(Settled — ADR-0033)* — A message Sukoon was in the middle of sending
when it stopped (a crash or power cut). It may or may not have reached WhatsApp, so it is
never resent by itself; an Admin can press Send again.

**Background jobs** *(Settled — ADR-0031, ADR-0033)* — Work Sukoon does on its own while it's
running: sending waiting WhatsApp messages every minute, monthly statements, the daily
overdue check. Only one running copy of Sukoon does this at a time (it holds the **worker
lock**); they run only when Sukoon is started with `python -m sukoon.run`.

**Archived Khata** *(Settled — ADR-0026)* — A customer removed from the Khata list and
the till's picker, with all their purchases and payments kept. Only possible at a
zero balance; a customer with no history at all is deleted instead.

## Technical terms

**SKU** *(Settled)* — Stock Keeping Unit. The shop's internal shelf/stock-taking
code (e.g. `OIL-5021`), unique across the catalog. Distinct from a barcode.
Auto-generated on product create as `{category-prefix}-{running number}`, and
editable by an Admin. See ADR-0018.

**Barcode / QR code** *(Settled)* — The scannable code physically on the product.
Usually the manufacturer's EAN/UPC (e.g. `8964000109283`). Unique across the
catalog, enforced at the database level.

**Internal barcode** *(Settled)* — A barcode Sukoon generates for goods with none
from a manufacturer (loose atta, unbranded items): `SK-` + a zero-padded number,
encoded as Code 128. The `SK-` prefix guarantees it can never collide with a real
numeric EAN-13. See ADR-0018.

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

**Till name** *(Settled)* — A terminal's human-facing label (e.g. "Till 2"),
stored in a long-lived cookie on that PC/browser, not tied to whoever is signed
in. Set once via a one-time prompt on the Till; recorded on `sale.terminal_label`
at checkout and shown on Sale Complete and the receipt. No server-side registry
of "known tills" exists — naming, not registration. See ADR-0023.

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

---

## Phase 7 — packaging, backup and recovery (added 2026-09-17, grill session)

**Installer** *(Settled)* — The single file the shop owner (or the developer) runs to
put Sukoon on the shop PC. It creates the program's folders, its Windows account and
start-up task, its data folder and a firewall rule — everything a working shop needs
that isn't the program itself.

**Shop PC (the server)** *(Settled)* — The one computer in the shop that holds Sukoon
and the data. Every other till is only a browser pointed at it, so if this machine is
off, the shop cannot sell.

**Background task** *(Settled)* — Sukoon's server, started by Windows when the PC boots,
before anyone signs in. It is what keeps the tills working after an unattended restart.

**Sukoon account** *(Settled)* — The dedicated Windows account the installer creates for
that background task, with a password generated by the installer that nobody types. The
WhatsApp key is encrypted for this account and no other ([ADR-0035](adr/0035-how-sukoon-starts-on-windows.md)).

**Data folder** *(Settled)* — `C:\ProgramData\Sukoon\`, where the database, logs, local
backups and the WhatsApp key live. Fixed on every install, kept when Sukoon is
uninstalled ([ADR-0036](adr/0036-where-the-shops-data-lives.md)).

**Snapshot (backup)** *(Settled)* — One safe copy of the whole database, taken while the
shop is still selling, compressed and encrypted before it leaves the PC. Not a plain file
copy, which can miss recent sales.

**Object storage** *(Settled)* — Cloud storage that holds files rather than running a
database. Where Sukoon's encrypted snapshots are kept, so a fire or a dead disk cannot
destroy the shop's books.

**Recovery sheet** *(Settled)* — The printed page produced once at setup, carrying the key
that unlocks the backups. Without it every backup is unreadable, so it is kept away from
the shop ([ADR-0037](adr/0037-offsite-backup-and-restore.md)).

**Backup self-check** *(Settled)* — Sukoon's weekly proof that recovery would actually
work: it downloads its own latest backup, decrypts it, opens it, and checks the newest
sale is there. A backup that cannot be opened should fail on a quiet Tuesday, not in a
disaster.

**Restore drill** *(Settled)* — A full rehearsal of the disaster: wipe the machine,
install fresh, restore from the cloud copy, confirm the books match. Done before handover.

**Recovery point** *(Settled)* — How much work a disaster can cost. Sukoon's is **15
minutes**: a dead disk loses at most the sales rung since the last snapshot.

**Reserved address** *(Settled)* — An instruction to the shop's router to always give the
shop PC the same network address, so the other tills' bookmarks never break.

**Clean machine test** *(Settled)* — Installing Sukoon on a Windows PC with no developer
tools, to prove the installer carries everything the shop needs. The shop's PC will never
have Python on it, so a test on a developer's machine proves nothing.

**Code signing** *(Settled)* — Paying a certificate authority so Windows shows a named
publisher instead of a security warning. Sukoon ships unsigned for this one shop
([ADR-0038](adr/0038-packaging-installation-and-delivery.md)).

**Machine-installed printer** *(Settled)* — A printer set up for the whole computer rather
than for one person's Windows login. Sukoon's receipts are printed by a background account,
which may not see a printer installed by the owner
([ADR-0039](adr/0039-receipt-printing-on-windows.md)).

**Litestream** *(Rejected for this project)* — A tool that continuously streams a SQLite
database to cloud storage, seconds behind. It was the best fit for Sukoon's backup until
its own release notes were checked: Windows is not an officially supported platform.

**Turso / libSQL** *(Not adopted)* — A hosted database that genuinely speaks SQLite, with a
local file kept in sync with a cloud copy. Closest thing to "SQLite in the cloud", but it
changes the database driver the whole app uses, and its offline-write behaviour is
unverified.

**Fixed address (static IP)** *(Settled)* — An address set on the shop PC itself instead
of asked for from a router. Sukoon's second supported network setup, for a shop wired
through a plain switch or with a router nobody can get into
([ADR-0038](adr/0038-packaging-installation-and-delivery.md) §10-B).
