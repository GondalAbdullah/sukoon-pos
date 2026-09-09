# Sukoon — Project Context

**The single source of truth.** Anyone, human or agent, starting cold should be able
to read this file and be fully oriented in five minutes. Updated at the end of every
work session, not just every phase.

---

## 1. Current phase and status

| | |
|---|---|
| **Phase** | Phase 0 — Project Setup & Grill Session |
| **Status** | **Phase 0 grill session and STOP AND ASK gate closed.** ADR-0001, 0003, 0004–0016 all Accepted. Remaining: the mechanical scaffolding steps (repo skeleton, venv, Flask app, config, logging, pytest) have not started. |
| **Last session** | 2026-09-06 |
| **Next action** | Begin Phase 0's remaining mechanical steps: repo skeleton, virtualenv, base Flask app, environment-based config, logging, pytest scaffold, smoke test confirming `flask run` serves a placeholder page. |

Nothing has been implemented. There is no application code in this repository yet,
and that is correct: Development Specification 13, step 3 says the agent must tell
the human it is time to run the grill session **and wait**, and Operating Rule 1
makes skipping it a rule violation rather than a shortcut.

## 2. Decisions made so far

| ADR | Decision | Status |
|---|---|---|
| [0001](adr/0001-technology-stack.md) | Technology stack — Flask + SQLite + htmx/Alpine/Tailwind, PyInstaller + Inno Setup | **Accepted** |
| [0002](adr/0002-initial-data-model.md) | Initial data model (original draft) | **Superseded by 0016** |
| [0003](adr/0003-module-boundaries.md) | Module boundaries — layered tree, `services/` never imports Flask | **Accepted** |
| [0016](adr/0016-consolidated-data-model.md) | **Consolidated schema** — every table as it now stands, all nine amendments merged, three prose-only gaps closed, invoice-counter yearly reset | **Accepted** |
| [0004](adr/0004-quantity-representation.md) | Quantity stored as integer thousandths of a unit; `allows_fractional` is presentation-only | **Accepted** |
| [0005](adr/0005-weighed-item-entry.md) | Weighed items entered manually by weight or by amount; scan becomes a resolver chain; scale hardware deferred behind a seam | **Accepted** |
| [0006](adr/0006-document-authority.md) | Development Specification outranks the Design System on all technical matters; prototype is a style reference | **Accepted** |
| [0007](adr/0007-money-rounding.md) | Money stored in paisa but always whole rupees; round half-up once per line; typed amount is authoritative | **Accepted** |
| [0008](adr/0008-authentication-and-access-control.md) | Passwords for all users (no PIN); permission table; step-up auth for destructive actions; no discount feature | **Accepted** |
| [0009](adr/0009-multiple-barcodes-per-product.md) | A product has many barcodes, each optionally carrying a price override; stock stays one number | **Accepted** |
| [0010](adr/0010-label-production.md) | Labels are generated as an A4 PDF sheet printed on adhesive paper; no label printer purchased | **Accepted** |
| [0011](adr/0011-catalog-onboarding.md) | Bulk-entry screen plus scan-as-you-go with provisional products; a Cashier may create provisional products only | **Accepted** |
| [0012](adr/0012-product-field-requirements.md) | Product fields in three tiers; name and price always required; cost/category/threshold nullable; SKU nullable and deferred | **Accepted** |
| [0013](adr/0013-customer-phone-identity.md) | Phone duplicates flagged not constrained; numbers normalised; unverified numbers receive no financial detail | **Accepted** |
| [0014](adr/0014-credit-limit-enforcement.md) | Credit limit blocks a Cashier; Admin may override with step-up; override recorded on the ledger | **Accepted** |
| [0015](adr/0015-credit-terms-and-overdue-tracking.md) | Overdue = balance outstanding past credit terms since the last real payment (not refund/adjustment); FIFO rejected | **Accepted** |

No ADR may move to **Accepted** until the Phase 0 grill session has run.

## 3. Open questions awaiting human decision

### Blocking — Phase 0 cannot close

**B-1 — The `grill-with-docs` skill was not installed; a scaffold is now in place.**
Verified on 2026-09-06 that no `grill-with-docs` skill existed anywhere on this
machine — not under `~/.claude`, not in any plugin marketplace, not in the Cursor
skills directory. The skill is `disable-model-invocation: true`, so it is
human-invoked by design and the agent could not trigger it regardless.

Resolution chosen by the human: install it and run it. A scaffold now exists at
`~/.claude/skills/grill-with-docs/SKILL.md`. Its **frontmatter is reproduced exactly**
from Development Specification 1. Its **body was written by Claude**, because the
original body was not present on this machine or in any supplied document — that
provenance is stated in a note at the top of the file itself. If the original skill
body is found, it should replace the reconstruction.

Phase 0 remains open until the session has actually been run and ADR-0001, 0002 and
0003 have moved from Proposed to Accepted.

**B-2 — Development machine is Linux; the delivery target is Windows.**
This machine is Ubuntu 24.04 with Python 3.12. Phases 0–6 are unaffected: Flask,
SQLite, and the whole test suite run identically. Phase 7 cannot be done here at
all — PyInstaller produces host-platform binaries, Inno Setup is Windows-only,
pywebview needs the Windows WebView2 runtime, and every Phase 7 test is a clean-VM
Windows test. A Windows machine or VM must exist before Phase 7 starts. Flagging it
now rather than at Phase 7 so it can be arranged in parallel.

Note also that the stack pins Python **3.11+** and this machine has **3.12.3**. That
satisfies the floor, but the version the installer ships must be pinned and matched
deliberately at Phase 7, not inherited from whatever the dev machine had.

### Design and data-model questions for the grill session

Carried from ADR-0002. Each needs a decision; several will need their own ADR.

- ~~**O-1 — PIN or password?**~~ **RESOLVED 2026-09-08.** Passwords for every user;
  no PIN is built. Permission table from Phase 1; step-up re-authentication for
  destructive actions. Edit-price and refunds are Admin-only. See
  [ADR-0008](adr/0008-authentication-and-access-control.md), Accepted.
- ~~**O-2 — Fractional quantities.**~~ **RESOLVED 2026-09-08.** The shop sells both
  loose goods (weighed on a scale) and sealed packs. All quantities are stored as
  integer thousandths of a unit with a per-product `allows_fractional` presentation
  flag. See [ADR-0004](adr/0004-quantity-representation.md), Accepted.
- ~~**O-3 — Tax.**~~ **RESOLVED 2026-09-10.** Prices already include tax; the system
  computes nothing. `sale.tax_paisa` retained fixed at zero, same treatment as
  `discount_paisa`. See ADR-0008 addendum, Accepted.
- ~~**O-4 — Duplicate customers.**~~ **RESOLVED 2026-09-09.** Flagged, not
  constrained; different customers may share a number. Numbers are normalised before
  matching. New client requirement added: a number must be confirmed as the
  customer's own, and an unverified number receives no balances or amounts. See
  [ADR-0013](adr/0013-customer-phone-identity.md), Accepted.
- **O-18 — OTP phone verification.** Reserved as `phone_verified_method = 'otp'` but
  not built in v1: it needs internet when a Khata is opened, costs a provider message,
  and the WhatsApp adapter does not exist until Phase 5. **Trigger:** Phase 5
  completing plus the client wanting stronger proof than in-person confirmation.
- ~~**O-5 — Discounts and "loyalty".**~~ **RESOLVED 2026-09-08.** No discount
  mechanism is built. The prototype's "Loyalty discount applied" is mock dressing.
  A reduced price is handled by relabelling goods with a new barcode at the lower
  price; the data model for that is the next open question. See ADR-0008.
- ~~**O-6 — Credit limit.**~~ **RESOLVED 2026-09-10.** Blocks a Cashier; an Admin
  may override with step-up re-authentication; the override is recorded on the
  ledger with the authorising Admin's identity. See
  [ADR-0014](adr/0014-credit-limit-enforcement.md), Accepted.
- ~~**O-19 — Credit terms aging method.**~~ **RESOLVED 2026-09-10.** Account-level
  staleness, not FIFO. A customer is overdue if their balance is positive and their
  most recent genuine `payment` (or, failing that, their first `credit_sale`) is
  older than `credit_terms_days`. A refund or an adjustment does not reset the clock.
  See [ADR-0015](adr/0015-credit-terms-and-overdue-tracking.md), Accepted.
- **O-20 — Overdue reminder and monthly statement scheduling may collide.** Both are
  separate APScheduler jobs against the same customer. A customer overdue and due a
  statement in the same week should not receive two uncoordinated WhatsApp messages.
  Not yet resolved; noted while writing ADR-0015 rather than discovered at Phase 5.
- **O-11 — The fractional cart row is undesigned.** ADR-0005 requires a cart row that
  accepts a typed weight or a typed amount for loose goods. The Design System has no
  such component and the prototype shows only the whole-number stepper. Needs a
  design before Phase 3 builds the Till. Per ADR-0006, absence from the prototype
  means undesigned, not disallowed.
- **O-12 — Scale hardware integration is deferred.** Trigger: the shop acquires a
  scale and states the model, since both the label barcode format and the serial
  protocol are manufacturer-specific. Seams are in place (ADR-0005); nothing is built.
- ~~**O-13 — Reduced-price relabelling has no data model.**~~ **RESOLVED 2026-09-08.**
  A product has many barcodes via a `product_barcode` table, each optionally carrying
  a `price_override_paisa`. Stock remains a single number.
  See [ADR-0009](adr/0009-multiple-barcodes-per-product.md), Accepted.
- ~~**O-14 — How the physical label is produced.**~~ **RESOLVED 2026-09-09.** Sukoon
  generates an A4 label sheet as a PDF, printed on adhesive sticker paper with any
  ordinary printer. No label printer is bought. Revisit trigger: label printing
  becoming a daily routine. See [ADR-0010](adr/0010-label-production.md), Accepted.
- ~~**O-15 — Initial catalog onboarding is unplanned.**~~ **RESOLVED 2026-09-09.**
  A bulk-entry screen plus scan-as-you-go with provisional products. No CSV importer;
  trigger is the client producing an actual file. See
  [ADR-0011](adr/0011-catalog-onboarding.md), Accepted.
- ~~**O-16 — May a Cashier create a provisional product?**~~ **RESOLVED 2026-09-09.**
  Yes, and only a provisional one. Flagged, attributed, listed under "Needs
  completing", excluded from margin reporting. No approval queue, no guessed cost, no
  cap. See [ADR-0011](adr/0011-catalog-onboarding.md).
- **O-17 — Does the shop use its own SKU codes?** The column exists as
  `sku TEXT NULL UNIQUE` so nothing is blocked, and the wider question is parked at the
  client's request. **Trigger:** confirming whether Mr. Abdullah writes his own codes
  on shelf labels, supplier orders, or stock-taking sheets. If he does, a generated
  format should match what he already writes; if not, the column can be dropped or
  left permanently empty. Must be settled before Phase 2 closes.
- **O-7 — Refunds have no design.** Development Specification Phase 3 requires a
  returns/refund flow that reverses both stock and ledger. The Design System has no
  screen for it and the prototype has no entry point. A screen must be designed, or
  the flow deliberately scoped to a later phase.
- **O-8 — Second terminal registration.** The Settings mock lists
  "Second Till (Terminal 2) — Checking…", implying terminals register and report
  health. No such feature exists in the specification. Real feature or mock dressing?
- **O-9 — Sale Complete auto-advance.** The Design System (6, Figure 8) says the
  screen "offers an auto-advance countdown"; the prototype does not implement one.
  The Design System also names the prototype as the reference for interaction (10.5).
  Which is truth, and if the countdown is real, how many seconds?
- **O-10 — Insights date range.** The Insights screenshot shows
  Today / This week / This month controls; the prototype omits them. In scope for
  Phase 6 or not?

## 4. Known issues and deferred work

- **Prototype ships a dead stylesheet import.** `sukoon_prototype.html` contains
  `@import url('fonts_embed.css')` for a file that does not exist beside it; the
  five Inter weights are already inlined as base64 above it, so the prototype renders
  correctly and the import silently 404s. Harmless there — but it must not be carried
  into the real templates, where a missing local asset would be a genuine offline bug.
- **Prototype fonts are `woff`, the spec asks for `woff2`.** Design System 10.1
  specifies bundling Inter as woff2. The prototype embeds woff. Source proper woff2
  files for `/static/fonts/` rather than extracting the prototype's base64.
- **Design assets are in place and verified.** All nine reference screenshots named
  in Design System 6 are present in `docs/design/` and are nine genuinely distinct
  images (confirmed by checksum — their identical file sizes are an artefact of the
  export tool, not duplication).
- **Prototype tokens verified against the specification.** All eighteen colour
  tokens in the prototype's `:root` match the Design System Appendix exactly, and
  the file makes zero external network requests. It is safe to treat as the literal
  source of truth for colour, radius, and shadow values, as 0 of the Design System
  instructs.

## 4b. Deliberate deviations from the design reference

Design System 13 requires every intentional departure from a reference screenshot to
be recorded here.

- **Login screen (Figure 1) — PIN pad replaced by a password field.** The avatar row,
  greeting, radial wash, and status line are unchanged. Auto-submit on the fourth
  digit is gone; submission is now explicit. Cause: the client chose passwords for all
  users over PIN quick-switch. See ADR-0008.
- **Till cart row — a fractional quantity control is added.** The prototype's
  whole-number stepper cannot express 1.5 kg. Sealed-pack products keep the stepper
  exactly as designed; loose products gain typed weight and typed amount entry. Cause:
  the shop sells loose goods. See ADR-0004 and ADR-0005. Component still undesigned,
  tracked as O-11.
- **Till summary — the "Discounts" line is removed.** No discount mechanism exists in
  v1. See ADR-0008.

## 4c. STOP AND ASK — Phase 0 closing gate — CLOSED 2026-09-10

Per Development Specification Phase 0: *"Confirm the draft database schema before it
becomes the basis for Phase 1 migrations"* and *"Confirm the final module list (no
additions/removals) before coding begins."*

**Confirmed by the client, without amendment:**
1. The schema — [ADR-0016](adr/0016-consolidated-data-model.md). Accepted.
2. The module list — [ADR-0003](adr/0003-module-boundaries.md). Accepted.
3. The stack — [ADR-0001](adr/0001-technology-stack.md). Accepted.

**One follow-up question resolved during review, not requiring a fresh grill
session** (a display/behaviour detail, not a new design area): whether
`invoice_counter` resets yearly or counts continuously. **Resolved: resets on the
first sale of each calendar year**, matching the prototype's own numbering format.
Recorded as an addendum to ADR-0016.

**This gate is now closed.** Phase 1 may build its migration against ADR-0016.

## 5. Edge case and test matrix

Every case below must have a passing automated test before its owning phase can
close. Hardware-in-loop items are marked and take a recorded manual test instead.
This list grows as new cases are found.

### Inventory (Phase 2)
- [ ] Stock cannot go negative through the normal sale flow
- [ ] Duplicate barcode/QR assignment is rejected at the database level
- [ ] Every manual stock adjustment requires a reason and logs who and when
- [ ] Concurrent stock updates from two terminals in the same second resolve without lost updates
- [ ] Deleting a product with sales history is a soft delete, not a hard delete
- [ ] Low-stock alert fires exactly at the configured threshold boundary
- [ ] A loose product sells 0.75 kg and stock drops by exactly 750 milli-units
- [ ] A sealed-pack product cannot be sold fractionally — rejected server-side
- [ ] Stock displays as `1.5 kg` and `42 bags` from the same underlying column
- [ ] A quantity of zero is rejected at the till for both product kinds

### Weighed-item entry (Phase 3)
- [ ] Entering a weight produces the correct line total for a loose product
- [ ] Entering an amount produces the correct weight for a loose product
- [ ] The two entry modes agree within the settled rounding rule
- [ ] `quantity_source` is recorded correctly for all three v1 entry paths
- [ ] An unrecognised scanned code returns a calm not-found result, not an exception
- [ ] A sealed-pack product offers no amount-entry mode

### Money and rounding (Phase 3)
- [ ] `round_paisa_to_rupee` correct at 0, 1, 49, 50, 51, 99, 100, 149, 150
- [ ] The same function is symmetric for negative values (refunds mirror sales)
- [ ] A receipt's printed line totals sum exactly to its printed subtotal
- [ ] Every persisted money column holds a multiple of 100 paisa
- [ ] A typed amount that is not a whole rupee is rejected at input
- [ ] An amount-entry line stores exactly the amount typed, not a recomputed value
- [ ] A refund of an amount-entry line returns exactly what the customer paid

### Authentication and access control (Phase 1)
- [ ] A Cashier session hitting every Admin-only route receives 403, not a redirect
- [ ] Authorisation is denied when a permission code is absent, even for role `admin`
- [ ] Repeated failed logins lock the account, and the lock expires correctly
- [ ] A destructive action without a fresh step-up re-entry is refused
- [ ] A step-up entry authorises exactly one action and does not persist in the session
- [ ] No code path anywhere can set a non-zero discount in v1
- [ ] Session expiry mid-sale does not lose the cart

### Barcodes and relabelling (Phase 2)
- [ ] Two barcodes on one product both resolve to it, at their respective prices
- [ ] Selling via an override barcode deducts stock from the single shared count
- [ ] A barcode is unique across the entire catalog, enforced at database level
- [ ] Deactivating a barcode stops it resolving, without affecting historical lines
- [ ] A product's normal price is unaffected by an override barcode existing
- [ ] Creating an override barcode without step-up authentication is refused
- [ ] `sale_item.product_barcode_id` records which label produced the price
- [ ] A generated barcode image decodes back to the code it was generated from
- [ ] A label sheet PDF renders the expected number of labels per page
- [ ] Sheet geometry is configurable without a code change
- [ ] A product with no barcode can be assigned a generated one and then resolves at the till

### Catalog onboarding (Phase 2)
- [ ] Bulk entry commits a row and returns focus to the scan field
- [ ] Scanning an existing code in bulk entry jumps to it rather than duplicating
- [ ] An unknown barcode at the till offers inline creation and the sale then completes
- [ ] A product created at the till is flagged provisional
- [ ] Provisional products appear in the "Needs completing" filter
- [ ] Margin reporting excludes provisional products rather than assuming zero cost
- [ ] Completing a provisional product clears the flag
- [ ] A Cashier cannot edit an existing product's price, only create a provisional one

### Product field requirements (Phase 1)
- [ ] A product cannot be created with a null or empty name
- [ ] A product cannot be created with a null selling price
- [ ] A product with a null cost price is accepted and flagged provisional
- [ ] A product with no barcode is accepted and is **not** flagged provisional
- [ ] Two products may both have a null SKU; two may not share a non-null SKU
- [ ] Margin reporting reports unknown-cost products as unknown, never as zero cost

### Customer phone identity (Phase 4)
- [ ] All four spellings of one number normalise to the same canonical form
- [ ] An unparseable number is rejected or stored null, never guessed
- [ ] Saving a customer with an existing normalised number prompts for confirmation
- [ ] Two customers may share a number once confirmed
- [ ] An unverified number receives the neutral notice and never an amount
- [ ] A verified number receives full notifications
- [ ] A customer with no phone number can still hold a Khata and be sold to
- [ ] Verification records who confirmed it, when, and by which method

### Credit limit enforcement (Phase 4)
- [ ] A credit sale that would stay within the limit succeeds normally for a Cashier
- [ ] A credit sale that would exceed the limit is blocked for a Cashier
- [ ] The same sale succeeds for an Admin only after step-up re-authentication
- [ ] An override records both the authorising Admin and the ringing Cashier distinctly
- [ ] A customer with a null credit limit is never blocked
- [ ] The check compares balance after the prospective sale, not before it

### Credit terms and overdue tracking (Phase 4)
- [ ] A customer past their credit terms with an outstanding balance is flagged
- [ ] A customer with a null `credit_terms_days` is never flagged, regardless of balance
- [ ] A fully paid customer, even if once overdue, is not flagged
- [ ] A customer with a balance and no payment yet is aged from their first credit sale
- [ ] A payment resets the reference date to that payment's own timestamp
- [ ] A refund does not reset the reference date, even though it reduces the balance
- [ ] An adjustment does not reset the reference date, even though it changes the balance
- [ ] `days_overdue` matches a hand-calculated value for a known fixture
- [ ] An overdue reminder goes only to a verified number; an unverified one gets nothing
- [ ] The overdue sweep completes normally when the WhatsApp provider is unreachable

### POS / Billing (Phase 3)
- [ ] Discount cannot exceed the item or cart total
- [ ] Checkout is blocked on an empty cart
- [ ] Invoice numbering has no duplicates and no gaps under concurrent checkouts
- [ ] A sale and its inventory deduction commit atomically; a crash mid-sale leaves no partial state
- [ ] A printer being offline degrades to PDF and never blocks completing the sale
- [ ] Refunds correctly reverse both the ledger (if credit) and the inventory count

### Credit customers / Khata (Phase 4)
- [ ] Ledger balance maths is correct across mixed sequences of sales and partial payments
- [ ] A customer with an outstanding balance cannot be deleted
- [ ] Duplicate customers sharing a phone number are prevented or flagged (see O-4)
- [ ] Overpayment produces an explicit credit balance, not a silent or confusing negative

### WhatsApp notifications (Phase 5)
- [ ] Provider timeout or outage never blocks or delays sale completion
- [ ] Failed sends retry with capped, backed-off attempts, then land in a visible failure log
- [ ] No duplicate notification is sent for the same event
- [ ] Missing or invalid phone number is handled gracefully, with the sale still completing
- [ ] Monthly statement generation is correct across month and timezone boundaries

### Barcode / QR (Phase 2)
- [ ] Scanning an unregistered code gives a clear "not found" result, not a crash
- [ ] Scanner input cannot leak into the wrong form field
- [ ] Two products cannot share the same code

### Auth (Phase 1)
- [ ] Session expiry is handled without data loss mid-sale
- [ ] A cashier hitting an admin-only route gets a server-side 403, not just a hidden button

### Reports (Phase 6)
- [ ] A date range with no data renders an empty state, not an error
- [ ] Reports over a large dataset stay responsive

### Local network and offline operation (Phase 7)
- [ ] The server auto-starts correctly after a PC restart
- [ ] A locked or unexpectedly closed database file recovers cleanly on next start
- [ ] The documented backup restore procedure is tested, not assumed
- [ ] The server's LAN address does not silently change under the cashiers' feet

### Windows install and packaging (Phase 7)
- [ ] Fresh install succeeds on a clean Windows VM with no developer tools present
- [ ] Uninstall removes the application but preserves the database by default
- [ ] Upgrade-install preserves existing data
- [ ] Missing WebView2 runtime is detected and handled, not a silent crash

### Hardware-in-loop (Phase 8, manual)
- [ ] Real barcode scanner HID input resolves the correct product
- [ ] Real ESC/POS thermal printer produces a correct 80mm receipt

## 6. Session changelog

*Reverse-chronological. Newest first.*

### 2026-09-10 — Session 3 (continued): Phase 0 STOP AND ASK gate closed

**Done**
- Client reviewed and confirmed ADR-0016 (schema), ADR-0001 (stack), and ADR-0003
  (module boundaries) without amendment. All three flipped from Proposed to
  Accepted.
- One follow-up question, raised during my own re-read of ADR-0016 rather than by
  the client: whether the invoice counter resets each year or counts continuously.
  Confirmed this did not need a fresh grill-with-docs invocation — a display
  convention, not a new design area. Recommended and recorded a yearly reset,
  matching the prototype's own number format, as an addendum to ADR-0016.
- Explicitly noted for the client's benefit that a fresh `/grill-with-docs`
  invocation *will* be needed at Phase 5 (WhatsApp) and Phase 7 (Windows
  packaging), per Development Specification 1 — not before.
- The Phase 0 STOP AND ASK gate (4c) is now recorded closed.

**Open / next**
- Phase 0's mechanical steps have not started: repo skeleton, virtualenv, base Flask
  app, environment-based config, logging, pytest scaffold, smoke test. This is the
  first actual code in the project.
- Non-blocking items carried forward unchanged from the prior session: O-7, O-8,
  O-9, O-10, O-11, O-12, O-17, O-18, O-20.

### 2026-09-10 — Session 3: closing the grill, consolidating the schema

**Done**
- Resolved O-3 (tax): prices already include tax, system computes nothing.
  `sale.tax_paisa` retained fixed at zero, same treatment as discount. Addendum to
  ADR-0008.
- Resolved O-19 in the prior session's thread properly: consolidated all schema
  amendments (ADR-0004, 0007, 0008, 0009, 0011, 0012, 0013, 0014, 0015) into
  [ADR-0016](adr/0016-consolidated-data-model.md), a single current-state schema.
  ADR-0002 marked Superseded, body left untouched as history.
- Found and closed three fields referenced only in prior ADRs' prose, never
  formalised as columns: `product.created_by_user_id` (ADR-0011),
  `credit_ledger_entry.override_authorised_by_user_id` (ADR-0014), and
  `notification_queue.notification_type` missing its third value (ADR-0015). Named
  explicitly as gaps found during consolidation, not silently patched in.
- Added an explicit §4c STOP AND ASK section presenting the schema (0016), module
  list (0003), and stack (0001) for sign-off, per Phase 0's own closing gate —
  rather than self-reporting these as done.

**Found and reported**
- ADR-0001 and ADR-0003 were never independently stress-tested this session — every
  question raised was about the data model, not the stack or module boundaries.
  Stated plainly in §4c rather than silently marking them Accepted by default.

**Open / next**
- Awaiting human confirmation on ADR-0016, 0001, 0003.
- Non-blocking items carried forward: O-7 (refund screen undesigned), O-8
  (second-terminal mock), O-9 (auto-advance), O-10 (Insights date range), O-11
  (fractional cart component undesigned), O-12 (scale hardware, deferred),
  O-17 (SKU format, deferred), O-18 (OTP, deferred), O-20 (reminder/statement
  scheduling collision). None block Phase 1.

### 2026-09-09 — Session 2 (continued): grill-with-docs, part 1

**Correction to an earlier claim in this file.** ADRs 0004 through 0009 were written
on 2026-09-08 but were dated 2026-09-06 in their headers, and several stated that a
client decision was "confirmed on 2026-09-06". I carried the date forward from
session 1 instead of checking it. All six headers and the affected in-text claims are
now corrected to 2026-09-08, and this note is left here rather than the edit being
made silently. ADRs 0001-0003 were genuinely written on 2026-09-06 and are unchanged.

**Decisions reached:** ADR-0004 quantity in thousandths, ADR-0005 weighed-item entry,
ADR-0006 document authority, ADR-0007 money rounding, ADR-0008 authentication and
access control, ADR-0009 multiple barcodes per product, ADR-0010 label production.
All Accepted. Resolved O-1, O-2, O-5, O-13, O-14. Raised O-11 through O-15.

### 2026-09-06 — Session 1: Kickoff and documentation system

**Done**
- Read the Development Specification, the Design System, and the standards
  reference in full before touching anything.
- Confirmed the project directory was empty; initialised a git repository on `main`
  with a `.gitignore` that excludes secrets, the SQLite database and its WAL/SHM
  sidecars, backups, and build output.
- Created the living documentation system: this file, `docs/adr/` with a template,
  and `docs/glossary.md` seeded with thirty domain terms.
- Copied the design assets into `docs/design/` per Design System 11: the clickable
  prototype and all nine reference screenshots.
- Drafted ADR-0001 (stack), ADR-0002 (data model), ADR-0003 (module boundaries), all
  as **Proposed**, to serve as concrete material for the grill session to attack.
- Verified the prototype against the Design System: eighteen colour tokens match the
  Appendix exactly, and the file makes zero external network requests, so the
  offline-asset rule holds.

**Found and reported**
- The `grill-with-docs` skill is not installed on this machine (B-1). Phase 0 cannot
  close without it.
- The development machine is Linux and the target is Windows (B-2). Phase 7 is
  unrunnable here.
- Ten unresolved design and data-model questions (O-1 … O-10), several of which are
  genuine contradictions between the two specification documents rather than mere
  gaps. O-1 (PIN vs password) and O-2 (fractional quantities) are the two that are
  expensive to get wrong, because both are frozen by the Phase 1 migration.
- Two minor prototype defects: a dead `fonts_embed.css` import, and woff rather than
  woff2 fonts.

**A correction to my own first assumption:** I initially expected the design assets
to be absent, since only PDFs were provided in conversation. They were present on
disk under `~/Downloads`. Recorded here rather than quietly fixed, per the
honest-reporting standard.

**Decision taken this session**
- On B-1, the human chose: install the skill and run it, rather than substituting an
  inline interview or waiving the gate. A scaffold was installed to
  `~/.claude/skills/grill-with-docs/SKILL.md` with the specification's exact
  frontmatter and a Claude-authored body, labelled as such in the file.

**Open / next**
- Human invokes `/grill-with-docs` against ADR-0002 and ADR-0003.
- The session must resolve O-1 and O-2 at minimum, since the Phase 1 migration
  freezes both.
- On completion, ADR-0001/0002/0003 move to Accepted and Phase 0's remaining steps
  (repo skeleton, config, logging, pytest scaffold) can begin.
- Nothing else should start before that.
