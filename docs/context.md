# Sukoon — Project Context

**The single source of truth.** Anyone, human or agent, starting cold should be able
to read this file and be fully oriented in five minutes. Updated at the end of every
work session, not just every phase.

---

## 1. Current phase and status

| | |
|---|---|
| **Phase** | Phase 2 — Inventory & Product Management — **COMPLETE** |
| **Status** | Category + product CRUD, SKU auto-generation (ADR-0018), stock-in/out/correction with a mandatory reason and full audit trail, negative-stock prevention, barcode assignment + internal Code 128 generation + the resolver chain (ADR-0009), the A4 label-sheet PDF with configurable geometry (ADR-0010), low-stock alerting at the exact threshold boundary, and the Stock list. `catalog.manage` / `stock.adjust` permissions added (ADR-0019, Admin-only). **No migration** — every table already existed from ADR-0016. `ruff` clean, 107 tests green, 95% coverage (business-logic modules ≥ 90%). Templates are functional HTML; the Tailwind visual pass is deferred. |
| **Last session** | 2026-09-10 (session 7) |
| **Next action** | Begin **Phase 3 — POS & Billing** (highest-traffic, highest-risk): the Till cart (search/scan to cart, quantity + the loose-goods weight/amount entry from ADR-0005), Cash/Card/Credit payment, atomic race-safe invoice numbering, sale + inventory deduction in one transaction, ESC/POS receipt + PDF fallback, and the returns/refund flow. Note the **Phase 3 STOP AND ASK gate** (discount rules + refund policy) and the added ADR-0019 item (confirm/split `catalog.manage`/`stock.adjust`). |

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
| [0017](adr/0017-auth-implementation-parameters.md) | Phase 1 auth parameters — the v1 permission catalogue, lockout defaults (5 attempts / 15 min), 10-hour session, name-or-initials login, `role_permission` surrogate key, model-level CHECKs | **Accepted** |
| [0018](adr/0018-product-identity-codes.md) | Product identity codes — auto-generated category-prefixed SKU (`OIL-5021`), internal barcodes are Code 128 with an `SK-` prefix; `labels.py` in `receipts/`, new `settings_service`. Resolves O-17 | **Accepted** |
| [0019](adr/0019-phase-2-authorization.md) | Phase 2 authz — `catalog.manage` + `stock.adjust`, Admin-only; sell-price change and price-override barcode stay step-up. Clarifies ADR-0008 §4's loose "Phase 3" attribution | **Accepted** |

(Historical rule, now satisfied: no ADR could move to **Accepted** until the Phase 0
grill session had run. It ran on 2026-09-10; ADR-0017 onward are ordinary Phase-N
decisions.)

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
- ~~**O-17 — Does the shop use its own SKU codes?**~~ **RESOLVED 2026-09-10.** Yes.
  Sukoon auto-generates a category-prefixed SKU (`OIL-5021` style) on product create,
  editable by an Admin, shop-wide running number. See
  [ADR-0018](adr/0018-product-identity-codes.md), Accepted.
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

- **Deferred permission codes (from ADR-0017 / ADR-0008 §4).** Six action-groups —
  void a sale, create/delete a product, stock-in/out, adjust a ledger entry, record
  a Khata payment, export data — were parked for the Phase 3 STOP AND ASK gate. When
  that gate assigns them, `sukoon/services/permissions.py` and the seed must be
  updated, and a re-`flask seed` run. Phase 2 CRUD work will need at least the
  product/stock ones, so this likely surfaces at the **start** of Phase 2, not Phase 3.
- **`instance/` dev databases are gitignored.** `flask db upgrade` writes
  `instance/sukoon.db` (+ `-wal`/`-shm`); none of it is committed. The migration
  scripts under `migrations/` **are** committed.

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

### Module-list deviations from ADR-0003 (frozen at the Phase 0 gate)

ADR-0003's tree was confirmed "no additions/removals". Two Phase 2 additions,
recorded rather than smuggled (ADR-0018 §3):

- **`services/receipts/labels.py`** — label-sheet PDF + barcode images. A file in
  the existing `receipts/` package, not a new top-level module.
- **`services/settings_service.py`** — a thin typed accessor over the `setting` KV
  table. A genuine new module; it holds no policy and replaces every service
  poking `Setting` rows directly.

### Phase 2 UI deviations

- **Stock screens are functional HTML, not the Design System's visual language.**
  The Stock list (Figure 3) and the Add Stock modal (Figure 7) are implemented as
  plain forms and a full-page adjust form, not the labelled bars, segmented
  control, or modal. Structure honours what matters now — one adjust entry point
  per product, a mandatory reason on every movement, the three movement types. The
  Tailwind + htmx visual pass is a later phase. Consistent with the Phase 1 login
  screen's treatment.

## 4d. Phase 0 Definition of Done — verified 2026-09-10

Per Development Specification, Phase 0. Every box below was independently checked,
not just written — see "how verified" for what was actually run.

- [x] Repository boots locally from a clean checkout with documented setup steps.
      **How verified:** copied the working tree to a scratch directory, deleted
      `.venv`, `.git`, `.env`, logs, and all caches, then followed `README.md`
      verbatim (venv, `pip install -r requirements-dev.txt`, `.env` from the
      example, generate a key). `./scripts/run_tests.sh` and a real
      `flask --app sukoon.app run` both passed from that clean copy, not the
      working copy already known to work.
- [x] `context.md`, `docs/adr/`, and `glossary.md` exist and are populated.
- [x] grill-with-docs session completed; the schema (ADR-0016, which supersedes
      ADR-0002) and stack (ADR-0001) are Accepted.
- [x] Module list and top-level data model confirmed by the human (4c).
- [x] Empty test suite runs green — now two real smoke tests, both passing.
- [x] A smoke test confirms `flask run` serves a placeholder page. **How verified:**
      not just the pytest-flask test client — a literal `flask run` process was
      started, `curl`'d for a real HTTP 200, and its log output inspected, in both
      the working copy and the independent clean-room copy.

**Skeleton built, following ADR-0003's module boundaries exactly:**
`sukoon/{models,services,routes,templates,static,jobs}/`, each services subpackage
(`notifications/providers`, `receipts`) present as an importable package.
`config.py` (environment-driven, no hardcoded secrets — Operating Rule 6),
`logging_config.py` (rotating file handler), `extensions.py` (stub, populated
Phase 1), `app.py` (factory, currently one placeholder route). `tests/{pure,integration}/`
per the same ADR. `ruff` clean, `pytest` green, coverage wired up.

**A gap found and closed while verifying, not left for Phase 1 to discover:**
`.gitignore` did not actually cover `logs/` or `.ruff_cache/` — both would have been
committable. Added both before anything was staged.

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

## 4e. STOP AND ASK — Phase 1 closing gate — CLOSED 2026-09-10

**Confirmed by the client on 2026-09-10, without amendment:** the 15 models in
`sukoon/models/`, the initial migration generated from them, and the deliberate
implementation-level additions listed below (all recorded in ADR-0017 §5–6). The
schema is now frozen — any change is a new migration, never an edit to
`…_phase_1_initial_schema_per_adr_0016.py`.

---

*Original gate text, for the record:*

Per Development Specification Phase 1: *"Confirm the final field list per table
before this migration is treated as frozen — later changes must go through a new
migration, not an edit to this one."*

**What is being presented for sign-off:**

1. **The 15 models in `sukoon/models/`**, built field-for-field from
   [ADR-0016](adr/0016-consolidated-data-model.md). The initial migration
   (`migrations/versions/…_phase_1_initial_schema_per_adr_0016.py`) was
   autogenerated from them and verified to apply, roll back, and re-apply cleanly
   from an empty database.

2. **Deliberate additions beyond ADR-0016's literal schema block**, each an
   implementation detail rather than a design change, recorded in
   [ADR-0017](adr/0017-auth-implementation-parameters.md) §5–6:
   - `role_permission` gets a surrogate `id` PK; the real guarantee is a
     `UNIQUE(role, permission_id)`.
   - Named CHECK constraints implied by ADR-0016 prose but not written as blocks:
     `product.sell_price_paisa >= 0`, `product.cost_price_paisa IS NULL OR >= 0`,
     `length(trim(product.name)) > 0`, `length(trim(stock_movement.reason)) > 0`.
   - A constraint/index naming convention on `db.metadata` so Alembic can name and
     later alter constraints deterministically (SQLite needs this for batch ops).
   - `String` length caps on text columns (e.g. `product.name` 255). SQLite does
     not enforce them; they are documentation and carry forward to any future
     non-SQLite target.
   - Timestamp columns are timezone-aware UTC in Python; SQLite stores them naive
     and the auth code treats a naive value read back as UTC.

3. **No column in ADR-0016 was dropped, renamed, or retyped.** `invoice_counter`
   and `setting` are modelled but not yet used (Phase 3 / later).

**Until the human records approval here, Phase 2 does not begin.** After approval,
any schema change is a new migration, never an edit to this one.

## 4f. Phase 2 Definition of Done — SIGNED OFF 2026-09-10

Per Development Specification Phase 2. Phase 2 has **no STOP AND ASK gate**; this
section is the "present the DoD to the human before the next phase" step.
**The client reviewed and approved this DoD on 2026-09-10.** Phase 3 may begin.

| Checklist item | Status |
|---|---|
| Full CRUD for categories and products, covered by tests, including the edge cases | ✅ `test_inventory.py`, `test_stock_routes.py` — create/edit/delete (soft vs hard), search, provisional derive/clear, SKU generation + uniqueness |
| Barcode/QR assignment and lookup verified end-to-end | ✅ `test_barcodes.py` — assign, generate (`SK-` Code 128), resolver chain, price-override resolution, deactivation; duplicate rejected at service **and** DB level |
| Low-stock alert list verified against seeded data | ✅ `test_inventory.py::test_low_stock_list_fires_exactly_at_threshold`, `test_catalog_summary_counts`; boundary is `<=` |
| Negative-stock prevention under sale-triggered deduction | ✅ `test_stock_movements.py` — `InsufficientStockError`; the `movement_type='sale'` path shares the code, wired to the till in Phase 3 |
| Adjustment audit trail (who, when, reason, before/after) | ✅ every `stock_movement` row records all four; a blank reason is refused at the service and by a DB CHECK |
| A generated barcode decodes back to its code | ✅ `test_labels.py` — pattern + mod-103 checksum decode (true optical scan is Phase 8 manual) |

**Also verified:** `flask run` serves `/stock`, `/stock/bulk`, product detail, and the
adjust/barcode/label endpoints with no errors; a barcode typed into the Stock search
box resolves to its product (the "simulate a scan" check).

**Deferred out of Phase 2, with rationale:**
- **The Design System visual layer** (labelled stock bars, the Add Stock modal, htmx
  per-row swaps). Functional HTML now; the Tailwind pass is its own phase.
- **Scan-as-you-go at the till, provisional-create by a Cashier** — Phase 3, they
  belong with the till scan infrastructure (ADR-0011 §2).
- **Concurrent-write correctness** — Phase 3, with invoice-numbering.

**For the Phase 3 gate (added by ADR-0019):** confirm or split `catalog.manage` /
`stock.adjust`, and decide whether either needs step-up.

## 5. Edge case and test matrix

Every case below must have a passing automated test before its owning phase can
close. Hardware-in-loop items are marked and take a recorded manual test instead.
This list grows as new cases are found.

### Inventory (Phase 2)
- [x] Stock cannot go negative — `test_stock_movements::test_stock_out_cannot_drive_stock_negative`
      (the `movement_type='sale'` path shares this code; wired to the till in Phase 3)
- [x] Duplicate barcode/QR assignment is rejected at the database level
      — `test_barcodes::test_duplicate_barcode_is_rejected_at_the_database_level`
- [x] Every manual stock adjustment requires a reason and logs who and when
      — `test_stock_movements::test_stock_in_adds_and_records_before_after`, `::test_every_adjustment_requires_a_reason`
- [ ] Concurrent stock updates from two terminals in the same second resolve without lost updates
      *(Phase 3 — belongs with invoice-numbering concurrency)*
- [x] Deleting a product with history is a soft delete, not a hard delete
      — `test_inventory::test_delete_with_movement_history_is_a_soft_delete` (+ hard-delete when no history)
- [x] Low-stock alert fires exactly at the configured threshold boundary
      — `test_inventory::test_low_stock_list_fires_exactly_at_threshold`, `test_inventory_pure::test_stock_status_boundary`
- [x] A loose product sells 0.75 kg and stock drops by exactly 750 milli-units
      — `test_stock_movements::test_loose_product_sells_fractional_and_drops_by_exact_milli`
- [x] A sealed-pack product cannot be sold fractionally — rejected server-side
      — `test_stock_movements::test_sealed_pack_cannot_take_a_fractional_quantity`
- [x] Stock displays as `1.5 kg` and `42 bags` from the same underlying column
      — `test_stock_routes::test_stock_list_formats_quantity_from_the_shared_column`
- [x] A quantity of zero is rejected — `test_stock_movements::test_zero_quantity_is_rejected`
      (the till's own zero-guard for both product kinds is Phase 3)

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
- [x] A Cashier session hitting every Admin-only route receives 403, not a redirect
      — `tests/integration/test_auth.py::test_cashier_hitting_admin_route_gets_403_not_a_redirect`
- [x] Authorisation is denied when a permission code is absent, even for role `admin`
      — `::test_permission_check_is_by_code_not_role_name`
- [x] Repeated failed logins lock the account, and the lock expires correctly
      — `::test_lockout_after_five_failures_then_rejects_correct_password`, `::test_lockout_expires`
- [ ] A destructive action without a fresh step-up re-entry is refused *(Phase 3 — no
      destructive flow exists yet; `auth_service.verify_step_up` is built and unit-tested)*
- [ ] A step-up entry authorises exactly one action and does not persist in the session *(Phase 3)*
- [ ] No code path anywhere can set a non-zero discount in v1 *(columns default 0, no
      setter exists; assertable once the sale flow lands in Phase 3)*
- [ ] Session expiry mid-sale does not lose the cart *(Phase 3 — no cart yet)*

### Barcodes and relabelling (Phase 2)
- [x] Two barcodes on one product both resolve to it, at their respective prices
      — `test_barcodes::test_two_barcodes_resolve_to_one_product_at_their_own_prices`
- [ ] Selling via an override barcode deducts stock from the single shared count
      *(Phase 3 — resolver returns the right product+price now; sale deduction is Phase 3)*
- [x] A barcode is unique across the entire catalog, enforced at database level
      — `test_barcodes::test_duplicate_barcode_is_rejected_at_the_database_level` (+ service-level)
- [x] Deactivating a barcode stops it resolving — `test_barcodes::test_deactivating_a_barcode_stops_it_resolving`
      (row is never deleted, so historical lines are unaffected — ADR-0009)
- [x] A product's normal price is unaffected by an override barcode existing
      — `test_barcodes::test_two_barcodes_resolve_to_one_product_at_their_own_prices`
- [x] Creating an override barcode without step-up authentication is refused
      — `test_stock_routes::test_price_override_barcode_requires_step_up`
- [ ] `sale_item.product_barcode_id` records which label produced the price *(Phase 3)*
- [x] A generated barcode image decodes back to the code it was generated from
      — `test_labels::test_generated_barcode_pattern_decodes_back_to_the_code` (pattern + checksum;
      true optical scan is a Phase 8 manual test)
- [x] A label sheet PDF renders the expected number of labels per page
      — `test_labels::test_label_sheet_page_count_follows_geometry`
- [x] Sheet geometry is configurable without a code change
      — `test_stock_routes::test_label_geometry_is_configurable_via_settings`
- [x] A product with no barcode can be assigned a generated one and then resolves
      — `test_barcodes::test_generated_barcode_has_sk_prefix_and_resolves` (till scan is Phase 3)

### Catalog onboarding (Phase 2)
- [x] Bulk entry commits a row — `test_stock_routes::test_bulk_entry_commits_a_row`
      (returns to the scan field; the htmx per-row focus polish is the deferred visual pass)
- [x] Scanning an existing code in bulk entry jumps to it rather than duplicating
      — `test_stock_routes::test_bulk_entry_existing_code_jumps_to_product_not_duplicate`
- [ ] An unknown barcode at the till offers inline creation and the sale then completes *(Phase 3)*
- [ ] A product created at the till is flagged provisional *(Phase 3)*
- [x] Provisional products appear in the "Needs completing" filter
      — `test_inventory::test_provisional_products_appear_in_needs_completing_filter`, `test_stock_routes::test_list_needs_completing_filter`
- [ ] Margin reporting excludes provisional products rather than assuming zero cost *(Phase 6)*
- [x] Completing a provisional product clears the flag
      — `test_inventory::test_completing_a_provisional_product_clears_the_flag`
- [x] A Cashier cannot edit an existing product's price, only create a provisional one
      — `test_stock_routes::test_cashier_is_forbidden_from_every_management_route` (provisional-create is Phase 3)

### Product field requirements (Phase 1)
- [x] A product cannot be created with a null or empty name
      — `tests/integration/test_models.py::test_product_requires_a_non_blank_name`
- [x] A product cannot be created with a null selling price
      — `::test_product_requires_a_sell_price` (and `::test_negative_sell_price_is_rejected`)
- [x] A product with a null cost price is accepted and flagged provisional
      — `test_inventory::test_product_missing_tier_c_is_provisional`, `test_inventory_pure::test_provisional_when_any_tier_c_field_missing`
- [x] A product with no barcode is accepted and is **not** flagged provisional
      — `test_inventory::test_barcodeless_product_is_not_provisional`
- [x] Two products may both have a null SKU; two may not share a non-null SKU
      — `::test_two_products_may_both_have_null_sku`, `::test_duplicate_non_null_sku_is_rejected`
      (note: SKUs are now auto-generated per ADR-0018, so a null SKU is rare in practice)
- [ ] Margin reporting reports unknown-cost products as unknown, never as zero cost *(Phase 6)*

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
- [x] Scanning an unregistered code gives a clear "not found" result, not a crash
      — `test_barcodes::test_unknown_code_returns_none_not_an_exception` (`resolve_barcode` returns `None`)
- [ ] Scanner input cannot leak into the wrong form field *(Phase 3 — a till/focus concern;
      the keyboard-wedge behaviour matters where the scan field must always hold focus)*
- [x] Two products cannot share the same code
      — `test_barcodes::test_duplicate_barcode_is_rejected_by_the_service` (+ DB-level)

### Auth (Phase 1)
- [ ] Session expiry is handled without data loss mid-sale *(Phase 3 — no cart yet)*
- [x] A cashier hitting an admin-only route gets a server-side 403, not just a hidden button
      — `tests/integration/test_auth.py`, plus `tests/pure/test_module_boundaries.py`
      mechanically enforces ADR-0003 §1 (`services/` never imports Flask)

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

### 2026-09-10 — Session 7: Phase 2 built (Inventory & Product Management)

**Decisions taken (via client Q&A, then ADRs)**
- **O-17 resolved** — the shop does use its own product codes. SKUs auto-generate,
  category-prefixed (`OIL-5021` style), editable. → [ADR-0018](adr/0018-product-identity-codes.md).
- **Generated barcodes** are Code 128 with an `SK-` prefix (never collides with a
  real EAN-13; every 1D scanner reads it). → ADR-0018.
- **Contradiction found and flagged:** ADR-0008 §4 said "creating/deleting a
  product" and "stock-in/out" were deferred to the Phase 3 gate, but the spec
  builds them in Phase 2 with no gate. Client chose: Admin-only now
  (`catalog.manage` + `stock.adjust`), finer taxonomy + step-up question still goes
  to the Phase 3 gate. → [ADR-0019](adr/0019-phase-2-authorization.md).
- Two module-list additions beyond the Phase-0-frozen ADR-0003 tree, recorded in
  §4b: `services/receipts/labels.py` and `services/settings_service.py`.

**Done**
- `inventory_service.py` — category/product CRUD, SKU allocation, provisional
  derivation (ADR-0012), soft-vs-hard delete, search (name/SKU/barcode),
  `apply_stock_movement` (in/out/correction/sale/refund, negative-stock guard,
  fractional guard, full audit row), `compute_stock_status` + `low_stock_products`
  at the exact boundary, `catalog_summary`, the barcode resolver chain, assign /
  generate / deactivate barcode. No Flask import (enforced by the boundary test).
- `services/receipts/labels.py` — Code 128 PNGs (`python-barcode` + Pillow) and the
  A4 label-sheet PDF (ReportLab); geometry from `setting` keys with defaults.
- `services/settings_service.py` — typed `setting` KV accessor.
- `routes/stock.py` + templates — Stock list w/ summary + filters, product detail
  (with adjust / barcode / label forms), product form, bulk entry, category
  management. `catalog.manage` / `stock.adjust` gating; sell-price change and
  price-override barcode require step-up (`require_step_up` helper added to guards).
- `permissions.py` + seed updated with the two new codes (Admin-only).
- **No migration** — every table was already in the frozen ADR-0016 schema.
- Deps: `python-barcode`, `Pillow`, `reportlab`.
- `ruff` clean; **111 tests pass; 95% coverage** (inventory_service 94%, labels 94%).

**Sign-off**
- **Phase 2 DoD (§4f) approved by the client on 2026-09-10.** Phase 3 may begin.

**Open / next**
- Phase 3 — POS & Billing. Carries a STOP AND ASK gate (discount + refund policy)
  plus the ADR-0019 follow-up (confirm/split `catalog.manage` / `stock.adjust`).
- Non-blocking carryovers: O-7, O-8, O-9, O-10, O-11, O-12, O-18, O-20. LICENSE
  owner-name placeholder still open.

### 2026-09-10 — Session 6: Phase 1 built (Core Data Model & Auth)

**Done**
- **Models.** All 15 ADR-0016 tables as SQLAlchemy 2.0 typed models under
  `sukoon/models/`, split by area (`user`, `catalog`, `inventory`, `customer`,
  `sales`, `khata`, `notifications`, `system`), shape-and-constraints only per
  ADR-0003. Flask-Login's interface is implemented directly on `User` so
  `models/` needs no `flask_login` import.
- **Migration.** Flask-Migrate/Alembic set up; `migrations/` committed. Initial
  migration autogenerated from the models and verified **up → down → up from an
  empty database** — driven through the real `flask db` CLI in a subprocess
  (`tests/integration/test_migration.py`), which also proves the "no manual
  steps" DoD claim.
- **Auth (ADR-0008).** Password login/logout, Flask-Login sessions, Werkzeug
  hashing. `services/auth_service.py` holds every decision and imports no Flask
  (mechanically enforced by `tests/pure/test_module_boundaries.py`). Brute-force
  lockout with a pure, boundary-tested `compute_lockout`. `routes/guards.py`
  `permission_required` decorator → real server-side 403; `routes/admin.py`
  ships one permission-guarded probe route as the enforcement seam.
- **Permissions.** `services/permissions.py` — the six confirmed v1 codes and the
  role split. `sukoon/seed.py` + `flask seed` write them (idempotent) plus
  optional dev users and a sample catalogue; passwords come from the environment.
- **ADR-0017** written and Accepted: records the parameters ADR-0008 left open
  (permission catalogue, lockout defaults, session lifetime, name-or-initials
  login) and the two schema-level implementation choices flagged for the freeze
  gate (`role_permission` surrogate PK, model-level CHECKs).
- `ruff` clean; **40 tests pass; 99% coverage** (business-logic modules 100%).
- README, `.env.example` updated (migration + seed steps, auth env vars).

**Sign-off**
- **Phase 1 STOP AND ASK gate (§4e) closed** — client approved the frozen schema
  (the 15 models + the ADR-0017 §5–6 implementation additions) on 2026-09-10,
  without amendment. Phase 2 may begin.

**Open / next**
- Phase 2 (Inventory & Product Management) is next. Seed the deferred
  product/stock permission codes (§4) as its first step.
- Non-blocking Phase-0 carryovers unchanged: O-7, O-8, O-9, O-10, O-11, O-12,
  O-17, O-18, O-20. The LICENSE owner-name placeholder (session 5) is still open.

### 2026-09-10 — Session 5: pre-GitHub-push audit

Requested by the client before pushing publicly, for review by their senior.
This is repository-hygiene work, not a product/architecture decision, so
recorded here rather than as a new ADR.

**Audit performed**
- Scanned the **entire git history**, not just the working tree, for anything
  that shouldn't be public: `.env` has never been committed; no API keys,
  passwords, or private-key material appear in any diff, ever. Confirmed clean.
- Checked actual repository size for GitHub: `.git` is 3.5 MB despite 51 MB of
  working-tree PNGs — the design mockups compress very well. Not a concern.
- Checked commit author identity (`abdullah <99gondalabdullah@gmail.com>`, the
  client's real email) and confirmed with the client this is acceptable to be
  public, along with the client/shop-identifying details already present
  throughout `docs/` (Al-Rehman General Store, Mr. Abdullah, AsCode Solution).

**Decisions, confirmed by the client**
- Repo will be **public**. Client/shop details stay as they are; no redaction.
- **No Dockerfile.** Recommended against one: ADR-0001 deliberately chose an
  offline Windows desktop install over any containerized deployment model, and
  a Dockerfile would imply a deployment path that contradicts that. The
  existing three-command venv setup already gets a reviewer running in under a
  minute, so the narrower "convenience for review" case didn't clear its cost
  either.

**Done**
- `.gitignore`: added `.vscode/`, `.idea/`, `*.swp` (gap found during audit,
  harmless either way).
- `.gitattributes`: added, normalising line endings to LF — relevant given
  development happens cross-platform ahead of a Windows delivery target.
- `LICENSE`: proprietary, all-rights-reserved notice, since the repo is public
  but explicitly not open source. **Left a placeholder for the owner name** —
  genuinely unclear whether that should be the client's personal name or
  "AsCode Solution" as a company, and guessing felt worse than asking.
- `README.md`: substantially rewritten. It was setup-instructions only; it now
  opens with what the project is, states current phase status, and — the part
  that actually matters for a reviewing senior — points explicitly at
  `context.md` and `docs/adr/` as the real material to look at, not the Phase 0
  skeleton code.
- `.github/workflows/ci.yml`: a minimal GitHub Actions workflow running exactly
  `scripts/run_tests.sh`'s checks (ruff + pytest + coverage) on every push and
  PR to `main`. Validated as parseable YAML before committing.
- Re-ran the full test suite after all changes; still green, unaffected.

**Open / next**
- **The LICENSE placeholder needs a real name filled in before this is fully
  correct** — flagged to the client directly, not resolved here.
- Everything else from Phase 0's completion still applies unchanged; Phase 1
  is next.

### 2026-09-10 — Session 4: Phase 0 scaffolding, and Phase 0 complete

**Done**
- Built the repo skeleton exactly per ADR-0003: `sukoon/{models,services,routes,
  templates,static,jobs}/`, `config.py`, `logging_config.py`, `extensions.py`
  (stub), `app.py` (factory + one placeholder route), `tests/{pure,integration}/`.
- `requirements.txt` / `requirements-dev.txt` (intentionally scoped to what Phase 0
  needs, not the full ADR-0001 stack — later phases add their own packages as they
  start, rather than pinning versions months before they're used).
- `.env.example`, `pyproject.toml` (tool config only, no `[project]` table),
  `scripts/run_tests.sh`, `README.md` with real setup steps.
- Created the venv, installed dependencies, ran `ruff check` (clean) and `pytest`
  (2 passed) in the working copy.
- **Independently re-verified the "clean checkout" claim**, rather than trust the
  working copy: copied the tree to a scratch directory, deleted `.venv`, `.git`,
  `.env`, logs, and every cache, followed `README.md` verbatim, and confirmed both
  the test suite and a real `flask run` (curled for an actual HTTP 200, not just
  the test client) passed from that independent copy.
- Found and fixed a real gap during that verification: `.gitignore` did not cover
  `logs/` or `.ruff_cache/`. Both would have been committable had this not been
  caught before staging.
- Phase 0's full Definition of Done recorded as verified in 4d, with what was
  actually run against each item, not just a checkmark.

**Open / next**
- Phase 0 is complete. Phase 1 (Core Data Model & Auth) begins next session:
  SQLAlchemy models per ADR-0016, the first Alembic migration, password-based auth
  per ADR-0008.
- Non-blocking items carried forward unchanged: O-7, O-8, O-9, O-10, O-11, O-12,
  O-17, O-18, O-20.

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
