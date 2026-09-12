# Sukoon — Project Context

**The single source of truth.** Anyone, human or agent, starting cold should be able
to read this file and be fully oriented in five minutes. Updated at the end of every
work session, not just every phase.

---

## 1. Current phase and status

| | |
|---|---|
| **Phase** | **Phase 3.5 — Visual Pass ([ADR-0022](adr/0022-dedicated-visual-pass.md)) — DESIGN DoD PRESENTED, one question open.** Phase 3 functionally complete and signed off (§4h). |
| **Status** | Phase 3.5 built out sessions 13–19 (toolchain, Login, Till, Sale Complete, terminal ID, Stock, Refunds, landing page, htmx pass — see §4i). **Session 20: the Design System §13 DoD side-by-side, done for real** — fresh screenshots of every built screen plus an actually-rendered receipt PDF compared against all 9 reference images, not a documentation exercise. Found and fixed three real issues: two undersized/no-hover action buttons (Till "Add", Refunds "Find") switched to the standard `.btn-ghost`; a receipt footer line that ran off the edge of the 80mm page for a long shop-contact string, fixed with real word-wrapping (measured, not guessed) and covered by new regression tests; and two missing Login details restored (the date line, per-avatar role labels). Full write-up, including the honoured deviations and **one open question for the client**, in §4j. `ruff` clean, **245 tests green** (3 new receipt word-wrap tests). |
| **Last session** | 2026-09-12 (session 20) |
| **Next action** | **Awaiting the client's answer to §4j's one open question** (the cart/stock stepper's button size: keep prototype-exact 26px, or bump to the Design System's 44px floor?) — then Phase 3.5 is formally closed and **Phase 4 (Khata / credit customers)** begins. **Notes:** credit-limit enforcement (ADR-0014) is Phase 4. The session cart does not survive session loss (§5 Auth item, deferred). |

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
| [0020](adr/0020-phase-3-refund-and-discount-policy.md) | Phase 3 gate — no discounts (confirmed); refund = Cashier initiates / Admin approves + step-up; original invoice required, partial refunds, auto-restock (+ damaged flag), ledger reversal for credit sales; new `refund`/`refund_item` tables; `catalog.manage`/`stock.adjust` stay coarse. Refines ADR-0008 §4, resolves O-7 | **Accepted** |
| [0021](adr/0021-invoicing-module-purity.md) | `invoicing.py` stays pure (rule 3 wins over ADR-0003's contradictory module-list gloss); the atomic invoice claim lives in `sales_service` | **Accepted** |
| [0022](adr/0022-dedicated-visual-pass.md) | Phases 1–3 stay functional HTML; **one dedicated visual pass ("Phase 3.5") after Phase 3, before Phase 4** converts every template to the Design System; Phases 4–6 built styled from the start. Deviates from Dev Spec §5.1's style-as-you-go | **Accepted** |
| [0023](adr/0023-till-terminal-identification.md) | A till names itself once via a long-lived cookie (not at login, not server config); `sale.terminal_label` finally populated; shown on Sale Complete + both receipt renderers. Resolves O-8's labelling half; live terminal status stays open | **Accepted** |

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
- ~~**O-11 — The fractional cart row is undesigned.**~~ **RESOLVED 2026-09-11.**
  Designed: a loose product (`allows_fractional = 1`) row replaces the stepper with
  an inline-expanding control — a two-segment **Weight (kg) / Amount (Rs)** toggle
  (same component as the Add Stock modal), one input, the other direction shown as a
  live `≈` preview. Added-but-not-yet-weighed rows commit in an amber **"needs
  weight"** state; checkout is blocked until every loose line has a quantity.
  Collapses to a compact `0.750 kg` / `Rs 200 · by amount` pill once filled. Mockups:
  `docs/design/drafts/till-fractional-cart/`. Recorded in §4b.
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
- ~~**O-7 — Refunds have no design.**~~ **RESOLVED 2026-09-11 (policy + data model).**
  The Phase 3 gate settled the refund flow: Cashier initiates, Admin approves with
  step-up; original invoice required; partial refunds allowed; refunded goods
  auto-restock (per-line damaged flag); credit-sale refunds reverse the ledger. New
  `refund` / `refund_item` tables (new migration). See
  [ADR-0020](adr/0020-phase-3-refund-and-discount-policy.md), Accepted. **The
  screen's visual design is done too now** (session 17, Phase 3.5, §4i) — no
  reference screenshot exists for Refunds, so it uses the established
  card/panel/pill vocabulary consistently (ADR-0006 rule 4) rather than a literal
  mock recreation.
- **O-8 — Second terminal registration.** *(Partially resolved 2026-09-12.)* The
  Settings mock lists "Second Till (Terminal 2) — Checking…", implying terminals
  register and report health. Put to the client as a scoped choice; they chose the
  narrowest option — **identify which till rang up each sale**, not live
  registration/health-monitoring, and explicitly not independent/offline tills
  (ruled out as contradicting ADR-0001). See
  [ADR-0023](adr/0023-till-terminal-identification.md): a till names itself once
  via a cookie, `sale.terminal_label` is populated, shown on Sale Complete and both
  receipts. **Still open:** the live "Checking…" health-status half of the mock —
  no `terminal` table, no heartbeat, nothing server-side tracks which tills exist.
  Revisit if that's ever actually wanted.
- ~~**O-9 — Sale Complete auto-advance.**~~ **RESOLVED 2026-09-11.** The countdown is
  real (follows the Design System text; the prototype's silence is not a decision per
  ADR-0006). A quiet progress ring on "Start next sale" advances after **~8 seconds**;
  any key or tap cancels it and keeps the calm screen. Recorded in §4b. Mockup in
  `docs/design/drafts/till-fractional-cart/SaleComplete.dc.html`.
- **O-10 — Insights date range.** The Insights screenshot shows
  Today / This week / This month controls; the prototype omits them. In scope for
  Phase 6 or not?

## 4. Known issues and deferred work

- **Deferred permission codes (from ADR-0017 / ADR-0008 §4).** Product/stock codes
  were assigned in Phase 2 (ADR-0019). The Phase 3 gate assigned **refund**
  (ADR-0020): `sale.refund_initiate` for a Cashier, `sale.refund` + step-up for an
  Admin approval. Still unissued, awaiting their own decisions: **voiding a completed
  sale, adjusting a ledger entry, recording a Khata payment, exporting data.** When
  a decision lands, update `sukoon/services/permissions.py` (the seed is
  dict-driven — no code change there) and re-run `flask seed`.
- **`instance/` dev databases are gitignored.** `flask db upgrade` writes
  `instance/sukoon.db` (+ `-wal`/`-shm`); none of it is committed. The migration
  scripts under `migrations/` **are** committed.

- **Prototype ships a dead stylesheet import.** `sukoon_prototype.html` contains
  `@import url('fonts_embed.css')` for a file that does not exist beside it; the
  five Inter weights are already inlined as base64 above it, so the prototype renders
  correctly and the import silently 404s. Harmless there — but it must not be carried
  into the real templates, where a missing local asset would be a genuine offline bug.
- ~~**Prototype fonts are `woff`, the spec asks for `woff2`.**~~ **RESOLVED
  2026-09-11 (Phase 3.5).** Inter 400/500/600/700/800 (Latin subset) bundled as
  woff2 in `sukoon/static/fonts/` from `@fontsource/inter`, `@font-face` in
  `static/css/input.css` — no CDN (Design System §10.1). The prototype's base64
  woff was not used.
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
  exactly as designed; loose products (`allows_fractional = 1`) gain typed weight
  and typed amount entry. Cause: the shop sells loose goods. See ADR-0004 and
  ADR-0005. **Designed 2026-09-11 (O-11 resolved):** the stepper's slot holds an
  inline-expanding control — a two-segment *Weight (kg) / Amount (Rs)* toggle (the
  Add Stock modal's segmented-control component), one input, a live `≈` preview of
  the other direction; collapses to a compact value pill once entered. A loose line
  with no quantity yet sits in an amber *"needs weight"* state and blocks checkout.
  Mockups: `docs/design/drafts/till-fractional-cart/` (published as an Artifact).
- **Till summary — the "Discounts" line is removed.** No discount mechanism exists in
  v1. See ADR-0008 and ADR-0020.
- **Sale Complete — an auto-advance countdown is added (O-9 resolved 2026-09-11).**
  The Design System (6, Figure 8) says the screen "offers an auto-advance countdown";
  the prototype omits it. Per ADR-0006 the prototype's omission is not a decision, so
  the Design System text governs: a quiet progress ring on "Start next sale" advances
  after ~8 seconds; any key or tap cancels it. Mockup:
  `docs/design/drafts/till-fractional-cart/SaleComplete.dc.html`.

### Module-list deviations from ADR-0003 (frozen at the Phase 0 gate)

ADR-0003's tree was confirmed "no additions/removals". Two Phase 2 additions,
recorded rather than smuggled (ADR-0018 §3):

- **`services/receipts/labels.py`** — label-sheet PDF + barcode images. A file in
  the existing `receipts/` package, not a new top-level module.
- **`services/settings_service.py`** — a thin typed accessor over the `setting` KV
  table. A genuine new module; it holds no policy and replaces every service
  poking `Setting` rows directly.

### Phase 2 UI deviations

- ~~**Stock screens are functional HTML, not the Design System's visual language.**~~
  **SUPERSEDED 2026-09-12 (Phase 3.5, session 16).** The Stock list now has the
  labelled stock-level bar and stat cards (Figure 3), and the Add Stock modal
  (Figure 7) is a real `<dialog>` with the segmented control and a live preview.
  See §4i.

### Phase 3 UI deviations

**The design DoD for Phases 1–3 is deferred to a single visual pass ("Phase 3.5")
after Phase 3 and before Phase 4 — [ADR-0022](adr/0022-dedicated-visual-pass.md),
Accepted.** Everything below is intentionally-unstyled and gets converted there.

- **The Till (Figure 2) and Sale Complete (Figure 8) are functional HTML.** Plain
  forms that reload, not the single-screen cart with live totals, the three payment
  pills, or the full-bleed calm moment. What is honoured: the scan field is the
  first control, sealed packs use a stepper, loose goods use the "needs weight" /
  typed-weight / typed-amount row from §4b (no toggle yet — both inputs shown),
  there is no discount line, and Sale Complete shows the invoice, change, and an
  8-second `meta refresh` in place of the O-9 auto-advance ring. The Tailwind/htmx
  pass and the §4b design are a later phase.
- **The cart is stored in the signed session, not a DB draft.** Simple and
  adequate for this shop's small carts; the cost is that a session lost mid-sale
  loses the cart (§5 Auth item, left unchecked). A `draft_sale` table is the fix
  if that becomes a real complaint.
- **The Khata customer is entered as a raw ID on the Till.** The customer picker
  (Figure 2's "Walk-in customer" chip) is Phase 4 work with the rest of Khata.

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

## 4g. STOP AND ASK — Phase 3 gate (discount + refund policy) — CLOSED 2026-09-11

Per Development Specification Phase 3: *"Confirm discount rules (max discount %, who
can apply it) and refund policy before this logic is locked in — both directly
affect the ledger and stock correctness."* Plus the ADR-0019 carry-over.

**Asked of the client and answered on 2026-09-11.** Full reasoning and the data
model are in [ADR-0020](adr/0020-phase-3-refund-and-discount-policy.md), Accepted.

1. **Discounts — none, confirmed.** v1 builds no discount mechanism (reaffirms
   ADR-0008 §6). `discount_paisa` / `line_discount_paisa` stay fixed at zero; a test
   asserts no code path can set them. Nothing new is built.
2. **Refund authority — Cashier initiates, Admin approves.** Refines ADR-0008 §4
   ("Admin only"). A Cashier may *start* a refund (`sale.refund_initiate`), creating
   a `pending_approval` row that moves no stock and no money. An Admin *approves* it
   with step-up (`sale.refund`). No unattended-Cashier path, no value cap. Both user
   ids are recorded on the refund.
3. **Refund mechanics — all four rules.** (a) The original invoice is required; a
   line can't be over-refunded. (b) Partial refunds allowed per line / per quantity;
   `manual_amount` loose lines are whole-line only and return exactly what was paid.
   (c) Refunded goods auto-restock via a `refund` stock movement on approval — with
   a per-line `restock` flag an Admin can untick for damaged returns (a flagged
   addition beyond the literal answer; default restocks). (d) Credit-sale refunds
   post a negative `credit_ledger_entry` and move no cash; cash/card sales refund
   from the drawer.
4. **`catalog.manage` / `stock.adjust` — stay coarse, Admin-only, no step-up.**
   Closes the ADR-0019 open item. A finer split / manager-role subset is declined
   for v1 (revisit when a third role exists).

**Consequences recorded:** Phase 3 carries a **new migration** (`refund` +
`refund_item` — first since the Phase 1 freeze) and a two-step refund workflow.
`sale.refund_initiate` added to the permission catalogue (Cashier + Admin).

**This gate is now closed.** Phase 3 build may proceed. (The Till *UI* still waits on
O-11, a design question, not a gate.)

## 4h. Phase 3 Definition of Done — SIGNED OFF 2026-09-11

**The client reviewed and approved the Phase 3 functional DoD on 2026-09-11 and
directed that the ADR-0022 visual pass (Phase 3.5) begin.** Phase 3 (POS &
Billing) is functionally complete.

Per Development Specification Phase 3. The STOP AND ASK gate (§4g) is already
closed; this was the "present the DoD before the next phase" step. **Functional
HTML only** — the Design System visual layer for these screens is
[ADR-0022](adr/0022-dedicated-visual-pass.md)'s Phase 3.5, now in progress.

| Checklist item | Status |
|---|---|
| A full sale journey (search/scan → cart → payment → invoice → receipt → stock update → saved transaction) | ✅ `test_till.py` drives scan → cart → checkout → Sale Complete; `test_sales.py::test_a_full_cash_sale_persists_one_consistent_transaction` asserts the invoice, subtotal/total, `sale_item` snapshots, stock deduction and movement rows in one go; `test_receipts.py` covers the receipt leg |
| Receipt output verified against a real or simulated ESC/POS printer | ✅ `test_receipts.py` — a `file` printer receives the exact ESC/POS bytes (`::test_a_working_printer_prints`), the byte stream carries the invoice + a paper-cut command, the 80 mm PDF renders. Real thermal hardware is the Phase 8 manual test |
| Refund flow independently tested end-to-end | ✅ `test_refunds.py` — 20 tests: initiate (Cashier) → pending, approve (Admin + step-up) → restock + ledger reversal + `sale.status` transition, reject, damaged-no-restock, over-refund block, mid-approval failure rolls back |

**Also verified (Required Tests, Development Spec Phase 3):**
- Concurrent-checkout race on invoice numbering — `test_invoice_concurrency.py`, 50 threads, no dupes/gaps.
- Cart edge cases — empty-cart checkout blocked (`test_till`, `test_sales`); discount-exceeding-total is **n/a**, no discount mechanism exists (ADR-0020).
- Transaction atomicity — `test_sales.py::test_a_failure_mid_sale_leaves_no_partial_state` (also asserts the invoice number is released).
- Printer-offline fallback — `test_receipts.py` (unreachable printer → sale completes, PDF offered).
- Refund reverses stock and ledger — `test_refunds.py`.

**Deferred out of Phase 3, with rationale:**
- **The Design System visual layer** for every Phase 1–3 screen → ADR-0022 Phase 3.5, in progress (§4i).
- **Session-loss-mid-sale cart survival** → a `draft_sale` table if it becomes real (§4b).
- **Credit-limit enforcement on a credit sale** → Phase 4 with the rest of Khata (ADR-0014).
- **The Khata customer picker** on the Till (raw ID for now) → Phase 4.
- **`quantity_source` values `usb_scale` / `scale_label`** → deferred behind the ADR-0005 seam until a scale exists (O-12).

## 4i. Phase 3.5 — Visual Pass tracker ([ADR-0022](adr/0022-dedicated-visual-pass.md))

**Toolchain (done, session 13):** `package.json` (build-time only — dev deps
`tailwindcss`, `alpinejs`, `htmx.org`, `@fontsource/inter`; `node_modules/`
gitignored), `tailwind.config.js`, `sukoon/static/css/input.css` +
`@layer components`, `scripts/build_css.sh` / `npm run build:css`. The compiled
`sukoon/static/css/tailwind.css` **is committed** (Dev Spec §5.1 — no Node in the
installer). Inter woff2 + Alpine + htmx vendored into `sukoon/static/`, served by
Flask, no CDN (Design System §10.1). `base.html` = the app shell.

**Rule:** this pass touches templates, `input.css`, and static assets only —
never routes or services — so the two-tier test suite stays green throughout.
(One narrow exception, session 13: `routes/auth.py` gained a render-context-only
change — passing the active-staff list and a greeting string to the login
template — no behaviour change, noted there rather than silently bent.) Any
intentional departure from a reference screenshot still goes in §4b.

**The htmx fragment-swap deferral is now closed (session 19).** It turned out
not to need a route change at all: every mutating Till form kept its existing
POST + redirect verbatim, and gained `hx-post` (same URL) + `hx-select="#till-body"`
+ `hx-target="#till-body"` + `hx-swap="outerHTML"`. htmx follows the server's
redirect itself (same as a browser would), receives the resulting full `/till/`
page, and `hx-select` lifts `#till-body` back out of it — so the view function
never learns or cares whether the request came from htmx. Zero coupling, zero
`HX-Request` branching, and the "templates only" rule for this pass held after
all. The interactive-verification concern was real, so it was met head-on rather
than waved off: `puppeteer-core` (dev dependency) drove a real headless Chrome
through add → stepper × 3 → remove and the loose-goods weight-entry path,
asserting zero full-page navigations and correct DOM state at each step.

| Screen (Design System figure) | State |
|---|---|
| `base.html` app shell — nav rail + top bar (§5) | ✅ session 13 |
| Login (Figure 1) | ✅ session 13 — radial wash, avatar row, greeting, Alpine reveal; ADR-0008 password deviation kept |
| Till (Figure 2) + Sale Complete (Figure 8) | ✅ session 14 — cart cards, sealed stepper, §4b loose row (Alpine segmented weight/amount toggle + live ≈ preview), payment pills, cash quick-amounts + live change preview, real O-9 countdown ring (Alpine, cancels on key/tap) |
| Stock list / detail / form / bulk / categories (Figures 3, 7) | ✅ session 16 — stat cards, labelled stock bar (reads `compute_stock_status`, never full at zero), a real Add Stock `<dialog>` modal with the segmented control + live preview |
| Refunds (find / sale / pending) — O-7 pixels | ✅ session 17 — established vocabulary (no reference screenshot exists), live per-line refund-amount preview |
| `placeholder.html` (landing) | ✅ session 18 — "Welcome back" + Till/Stock/Refunds tiles (authenticated), a plain sign-in prompt (anonymous); no reference screenshot exists |
| htmx fragment-swapping pass | ✅ session 19 — Till cart mutations swap `#till-body`; verified in a real browser via `puppeteer-core` |
| Design DoD side-by-side vs all 9 screenshots (Design System §13) | ✅ session 20 — see §4j; one open question for the client |

## 4j. Phase 3.5 — Design Definition of Done (Design System §13) — presented 2026-09-12

Per Design System §13: *"no phase that touches UI closes until all of the
following are true."* Nine checklist bullets, checked against real rendered
output (fresh screenshots + a rendered receipt PDF, not the templates read
cold), plus a screen-by-screen comparison against the reference screenshot
each has. Two real gaps were found and fixed in this same session, not just
logged for later.

### The nine bullets

1. **No technical/implementation terms on any cashier/customer screen** — ✅
   PASS. Grepped every template and every `flash()` string in `routes/` for
   database/API/HTTP/JSON/exception-shaped language; the only hits were Jinja
   variable names and SVG markup, never rendered text.
2. **Exactly one dominant focal point per screen** — ✅ PASS. Till: the Rs
   total (44px). Sale Complete: the checkmark, then the change figure. Stock:
   the table (stat cards are deliberately smaller/secondary). Login: the
   avatar row.
3. **Coral only for negative/urgent, Amber only for caution, never raw
   red/orange/yellow** — ✅ PASS. Grepped templates, `input.css`, and
   `tailwind.config.js` for any `red-*`/`orange-*`/`yellow-*` utility or raw
   hex — zero hits. Every negative state uses `coral`, every caution state
   uses `amber`.
4. **Every status indicator pairs colour with a text label** — ✅ PASS. Stock
   bar, refund status, provisional badge — all render the word, not just the
   tint.
5. **Every primary button ≥44×44px; the highest-frequency action is the
   largest control** — ⚠️ **found and fixed one real gap.** The Till's "Add"
   button and the Refunds "Find" button were a leftover ad-hoc small pill
   (~22px tall, no hover state) instead of the shared `.btn-ghost` component —
   switched both to `.btn-ghost` (≥44px, hover included). **One item left
   open for you, below:** the cart stepper's ± keys are 26×26px, matching the
   literal prototype's own stepper size (ADR-0006 ranks the prototype as the
   literal style source) — but that's under the Design System's own 44px
   floor. The two governing documents disagree with each other here; I didn't
   pick a side.
6. **Every interactive element has a visibly distinct default/hover/disabled
   state** — ✅ PASS (after the fix above). `.btn-primary`/`.btn-ghost`/`<a>`
   all carry `hover:` in their shared component definition, so every button
   built from them inherits it automatically; `.btn:disabled` is a distinct
   sunk/faint treatment, verified in the Till checkout button screenshot.
7. **Fonts and icons served locally; zero external requests** — ✅ PASS,
   verified by inspecting the actual shipped files, not assumed: grepped
   every template, `input.css`, the compiled `tailwind.css`, and both vendored
   JS files for `http(s)://`. The only two hits are inert — Tailwind's own
   license-comment banner and a string inside Alpine's unregistered-plugin
   *error message* (only prints to console if a missing plugin is invoked,
   never fetched). No live request leaves the page.
8. **Copy checked against §9** — ✅ PASS. Zero exclamation marks anywhere in
   templates. Every `flash()` message in every route read calmly and
   factually ("Stock updated.", "Too many attempts. Try again shortly.") —
   none blame the person. Empty states are full sentences ("Nothing in the
   cart yet — scan or search to add an item." — the Design System's own
   example, verbatim) not bare words.
9. **Side-by-side against the reference screenshot, deviations noted here** —
   see below.

### Side-by-side findings, by screen

**Login (Figure 1).** Close match after two small additions made this
session: the date line above the greeting, and a role label under each
avatar's name (both present in the reference, both missing before). The
reference's corner logo+store-name header bar and "Working normally, on this
device" status line were **not** added — the corner header would duplicate
the centred wordmark for no real gain, and fabricating a health-check line
we have no data for would be dishonest chrome (O-8 is deferred). Replaced my
own placeholder line ("· working offline-first", which was itself a stray
bit of implementation jargon) with a plain "Al-Rehman General Store". The
PIN-pad-to-password swap stays exactly as ADR-0008 already recorded.

**Till (Figure 2).** Structurally very close to the reference already — same
two-column layout, same stat treatment on the total, same stepper visual
language. No new deviations found beyond the already-recorded ones (loose-row
control, no Discounts line).

**Sale Complete (Figure 8).** Two differences, left as-is rather than
"fixed", because each has a reason: the reference's headline reads "All
done" where ours reads "Sale complete" — kept, because the Design System's
own body text calls this screen "Sale Complete" throughout and it's already
what the test suite encodes; and the reference shows a "Received / Change
due" two-column figure where we show only the change — kept, because the
Design System's own **written** spec for this screen says *"the checkmark,
headline, and change-due figure are the only things on screen"*, which is
what we built. Two governing documents (the screenshot and its own caption
text) disagree with each other; we followed the written spec.

**Stock list (Figure 3).** One real bug found and fixed already in session
16 (an out-of-stock item with no threshold showed a full bar) stays fixed.
One deliberate omission newly confirmed here: the reference repeats "Low" /
"Restock" as a badge next to the product name *and* in the stock-level
column; we show it once, in the stock-level column only, where the bar and
the words already carry it — showing it twice is the kind of redundant
"data slop" the design guidance itself warns against, not a gap.

**Add Stock modal (Figure 7).** The reference's quantity control is a
whole-number ± stepper; ours is a typed number field. Same reasoning as the
Till's loose-goods row (ADR-0004/0005) — a stock correction can be fractional
(a loose product's count is in kg, not whole units), and a ±1 stepper cannot
express that. Recorded as the same deviation family, not a new one.

**The printed receipt (Figure 9).** Rendered a real PDF and looked at it
directly rather than trusting the code. Found and fixed one real bug this
way: the footer line repeating the shop's contact details ran off the edge
of the 80 mm page for a contact string this long — thermal printers don't
wrap gracefully, they just cut it off. Added proper word-wrapping
(measuring actual string width, not guessing a character count) and used it
for both the header contact line and the new footer line. Also added, to
close two real gaps against the reference: a drawn logomark (a teal
rounded square with an amber dot — no image asset needed or available, so
drawn directly) above the shop name, and the footer repeating the shop's
contact so a customer checking the bottom of their receipt finds a number to
call. Left different on purpose: "Served by" (reference) vs "Cashier" (ours,
matches the rest of the app's own vocabulary); one line per item vs the
reference's inline "×N" (ours has to also carry a loose item's weight and
unit, which "×N" can't express cleanly).

**Refunds, the landing page.** No reference screenshot exists for either
(O-7's screen and the app's own landing page respectively) — built on the
established vocabulary per ADR-0006 rule 4, as already recorded when each
was built.

**Not yet built, correctly out of scope:** Khata (Figure 4, Phase 4),
Insights (Figure 5, Phase 6), Settings (Figure 6, not yet scheduled).

### The one open question for you

The cart stepper (Till, §4b) and the Add Stock modal's own ± stepper are
26–42px, under the Design System's 44px minimum touch target, but pixel-exact
to the prototype's own stepper (which ADR-0006 makes the literal style
authority). Keep the smaller, prototype-exact size, or bump to 44px for
touch reliability? No action taken either way pending your call — this
doesn't block anything else.

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
- [x] Concurrent stock updates from two terminals in the same second resolve without lost updates
      — `tests/integration/test_invoice_concurrency.py::test_concurrent_sales_of_one_product_do_not_lose_a_stock_update`
      (30 concurrent sales of one item, on-disk WAL). `apply_stock_movement`'s in/out/sale/refund path is now a single guarded relative `UPDATE … RETURNING`, not a read-then-write. **`correction` still writes an absolute level** — acceptable for a rare manual recount, noted for later.
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
- [x] Entering a weight produces the correct line total for a loose product
      — `tests/pure/test_pricing.py::test_weight_produces_the_correct_line_total`
- [x] Entering an amount produces the correct weight for a loose product
      — `test_pricing::test_amount_produces_the_correct_weight`
- [x] The two entry modes agree within the settled rounding rule
      — `test_pricing::test_the_two_modes_agree_within_the_rounding_rule`
- [x] `quantity_source` is recorded correctly (stepper / manual_weight / manual_amount)
      — `tests/integration/test_sales.py` (`::test_by_amount_line_stores_the_typed_amount_and_the_source` + the stepper/weight paths in `::test_a_full_cash_sale...`)
- [x] An unrecognised scanned code returns a calm not-found result, not an exception
      — `test_till::test_an_unknown_code_is_reported_not_added` (the Till shows "Nothing matched …"), `test_barcodes::test_unknown_code_returns_none_not_an_exception`
- [x] A sealed-pack product offers no amount-entry mode
      — `test_sales::test_a_sealed_pack_cannot_be_sold_by_amount` (service); the Till only renders weight/amount inputs for `allows_fractional` lines

### Money and rounding (Phase 3)
- [x] `round_paisa_to_rupee` correct at 0, 1, 49, 50, 51, 99, 100, 149, 150
      — `tests/pure/test_money.py::test_round_paisa_to_rupee_boundaries`
- [x] The same function is symmetric for negative values (refunds mirror sales)
      — `test_money::test_round_is_symmetric_about_zero`, `::test_line_total_is_symmetric_for_a_refund`
- [x] A receipt's printed line totals sum exactly to its printed subtotal
      — `receipt_body` prints each `sale_item.line_total_paisa` and the `sale.subtotal_paisa`,
      both already whole-rupee, and the subtotal is the sum of the lines by construction
      (`test_pricing::test_cart_subtotal_sums_already_rounded_lines`, `test_receipts`)
- [x] Every persisted money column holds a multiple of 100 paisa
      — `test_sales::test_persisted_money_columns_are_whole_rupees`, `test_pricing::test_every_line_total_is_a_whole_rupee`
- [x] A typed amount that is not a whole rupee is rejected at input
      — `test_sales::test_a_typed_amount_that_is_not_a_whole_rupee_is_refused`
- [x] An amount-entry line stores exactly the amount typed, not a recomputed value
      — `test_sales::test_by_amount_line_stores_the_typed_amount_and_the_source`, `test_pricing::test_manual_amount_line_stores_exactly_what_was_typed`
- [x] A refund of an amount-entry line returns exactly what the customer paid
      — `test_refunds::test_a_by_amount_line_is_whole_or_nothing` (refunds `line_total_paisa`, the typed Rs 200 — not a recomputed figure), `::test_line_totals_mirror_the_sale`

### Authentication and access control (Phase 1)
- [x] A Cashier session hitting every Admin-only route receives 403, not a redirect
      — `tests/integration/test_auth.py::test_cashier_hitting_admin_route_gets_403_not_a_redirect`
- [x] Authorisation is denied when a permission code is absent, even for role `admin`
      — `::test_permission_check_is_by_code_not_role_name`
- [x] Repeated failed logins lock the account, and the lock expires correctly
      — `::test_lockout_after_five_failures_then_rejects_correct_password`, `::test_lockout_expires`
- [x] A destructive action without a fresh step-up re-entry is refused
      — `test_refunds::test_admin_approve_needs_a_valid_step_up_password` (wrong / missing password → 403),
      `test_stock_routes::test_sell_price_change_requires_step_up`
- [x] A step-up entry authorises exactly one action and does not persist in the session
      — `require_step_up` reads `request.form` and holds no session state (guards.py); each refund
      approval re-prompts (`test_refunds`, `templates/refunds/pending.html`)
- [x] No code path anywhere can set a non-zero discount in v1
      — `record_sale` writes `discount_paisa=0` / `line_discount_paisa=0` unconditionally; the Till
      and refund forms have no discount field; `test_pricing`/`test_sales` assert whole-rupee totals
- [ ] Session expiry mid-sale does not lose the cart *(the cart now exists but lives in the
      signed session — it does NOT survive session loss. Deferred: a `draft_sale` table is the
      fix if this becomes a real complaint. §4b Phase 3 UI deviations.)*

### Barcodes and relabelling (Phase 2)
- [x] Two barcodes on one product both resolve to it, at their respective prices
      — `test_barcodes::test_two_barcodes_resolve_to_one_product_at_their_own_prices`
- [x] Selling via an override barcode deducts stock from the single shared count
      — the Till carries `product_barcode_id` + the effective price onto the `CartLine`;
      `record_sale` snapshots both and deducts the one `product.stock_quantity_milli`
      (`test_till::test_a_barcode_resolves_to_its_product` + `test_sales`)
- [x] A barcode is unique across the entire catalog, enforced at database level
      — `test_barcodes::test_duplicate_barcode_is_rejected_at_the_database_level` (+ service-level)
- [x] Deactivating a barcode stops it resolving — `test_barcodes::test_deactivating_a_barcode_stops_it_resolving`
      (row is never deleted, so historical lines are unaffected — ADR-0009)
- [x] A product's normal price is unaffected by an override barcode existing
      — `test_barcodes::test_two_barcodes_resolve_to_one_product_at_their_own_prices`
- [x] Creating an override barcode without step-up authentication is refused
      — `test_stock_routes::test_price_override_barcode_requires_step_up`
- [x] `sale_item.product_barcode_id` records which label produced the price
      — `record_sale` copies `CartLine.product_barcode_id` onto the `sale_item`; the Till sets it
      from the barcode resolver (`test_till::test_a_barcode_resolves_to_its_product`)
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
- [x] An unknown barcode at the till offers inline creation and the sale then completes
      — `test_till::test_an_unknown_code_offers_provisional_creation`, `::test_cashier_creates_a_provisional_product_at_the_till`
- [x] A product created at the till is flagged provisional
      — `test_till::test_cashier_creates_a_provisional_product_at_the_till` (name + price only → `is_provisional`, appears in "Needs completing", `created_by` = the Cashier)
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
- [n/a] Discount cannot exceed the item or cart total — no discount mechanism exists in v1 (ADR-0008 / ADR-0020); `record_sale` has no path that sets a non-zero discount
- [x] Checkout is blocked on an empty cart
      — `test_sales::test_checkout_is_blocked_on_an_empty_cart` (service), `test_till::test_an_empty_cart_cannot_be_checked_out` (route)
- [x] Invoice numbering has no duplicates and no gaps under concurrent checkouts
      — `tests/integration/test_invoice_concurrency.py::test_concurrent_claims_have_no_duplicates_and_no_gaps` (50 threads, on-disk WAL)
- [x] A sale and its inventory deduction commit atomically; a crash mid-sale leaves no partial state
      — `test_sales::test_a_failure_mid_sale_leaves_no_partial_state` (also asserts the briefly-claimed invoice number is released)
- [x] A printer being offline degrades to PDF and never blocks completing the sale
      — `test_receipts::test_an_unreachable_network_printer_falls_back_to_pdf`,
      `::test_checkout_completes_and_offers_a_pdf_when_no_printer`,
      `::test_issue_receipt_never_raises` (`issue_receipt` runs *after* the sale commits and cannot raise)
- [x] Refunds correctly reverse both the ledger (if credit) and the inventory count
      — `test_refunds::test_a_credit_sale_refund_reverses_the_ledger_and_moves_no_cash`,
      `::test_approving_restocks_and_completes_the_status_transition`,
      `::test_a_damaged_line_is_not_restocked`, `::test_a_failure_during_approval_leaves_the_refund_pending`

### Till terminal identity (Phase 3 addendum — ADR-0023)
- [x] A fresh browser with no `sukoon_terminal` cookie sees the naming prompt on the Till
      — `test_till::test_a_fresh_till_is_asked_to_name_itself`
- [x] Naming a till sets the cookie and the prompt does not reappear
      — `test_till::test_naming_a_till_sets_a_cookie_and_stops_asking`
- [x] A sale rung up after naming carries that `terminal_label`; before naming it stays NULL
      — `test_till::test_a_sale_rung_up_after_naming_carries_the_terminal_label`, `::test_a_sale_before_naming_has_no_terminal_label`
- [x] Renaming a till changes future sales, not past ones
      — `test_till::test_renaming_a_till_only_affects_future_sales`
- [x] A blank label does not overwrite an existing name
      — `test_till::test_a_blank_label_does_not_overwrite_an_existing_name`
- [x] The receipt (ESC/POS bytes and the PDF) shows the till's name when the sale carries one
      — `test_receipts::test_the_till_name_appears_when_the_sale_carries_one`

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

### 2026-09-12 — Session 20: the Design System §13 DoD, done against real output

Full write-up in §4j. Summary: went through all 9 checklist bullets and all 9
reference screenshots against fresh screenshots of the real running app (and,
for the receipt, an actually-rendered PDF, not the code read cold) — the
review this project's own rules require before a UI phase can close, done as
a real check rather than a formality.

**Found and fixed (not just logged):**
- Till's "Add" button and Refunds' "Find" button were an ad-hoc small pill
  (~22px, no hover state) instead of the shared `.btn-ghost` — switched both;
  now ≥44px with the standard hover treatment.
- The receipt's new footer contact line ran off the edge of the 80mm page for
  a long `shop.contact` string — thermal printers cut long lines off rather
  than wrapping them. Added real word-wrapping (`stringWidth`-measured, not a
  guessed character count) to both the header and footer contact lines.
  Caught by actually rendering a PDF and looking at it, not by reading the
  code. Regression-tested: `test_long_text_wraps_within_the_printable_width`
  asserts every wrapped line's measured width fits, `test_a_long_shop_contact_
  does_not_run_off_the_receipt` renders one end-to-end.
- Login was missing two details the reference has: the date line above the
  greeting, and a role label under each avatar's name. Added both (Alpine
  `x-text` for the date — no route change; the role was already on the `staff`
  query from session 13). Also dropped "· working offline-first" from my own
  placeholder status line — accurate but itself a stray bit of implementation
  jargon on a cashier-facing screen (DoD bullet 1).
- Receipt gained a drawn logomark (teal rounded square + amber dot — no image
  asset exists, so drawn directly in ReportLab) and a footer line repeating
  the shop's contact, closing two real gaps against Figure 9.

**Checked and confirmed clean, not assumed:** zero raw red/orange/yellow
anywhere (grepped `input.css` + `tailwind.config.js` + every template); zero
external network requests (grepped every template, the compiled CSS, and both
vendored JS files for `http`/`https` — the two hits are an inert license
comment and an error-message string, never fetched); zero exclamation marks
or blame-toned copy in any template or `flash()` call; every status pairs
colour with a text label.

**Deviations from a reference screenshot, considered and kept as-is (recorded
here, not silently decided):**
- Sale Complete says "Sale complete" where the mock says "All done" — kept,
  matches the Design System's own body text and the existing test suite.
- Sale Complete omits the "Received" figure the mock shows — kept, matches
  the Design System's own *written* spec for the screen ("the checkmark,
  headline, and change-due figure are the only things on screen").
- Stock list shows "Low"/"Restock" once (in the stock-level column) where the
  mock repeats it as a name badge too — kept single; showing it twice is
  redundant, not more informative.
- The Add Stock modal's quantity control is a typed field, not the mock's
  ±1 stepper — same reasoning as the Till's loose-goods row (ADR-0004/0005): a
  stock correction can be fractional, and a whole-unit stepper can't express
  that.

**One open question, not decided either way:** the cart/stock stepper's ±
keys are 26–42px — exact to the prototype's own stepper (ADR-0006's literal
style authority) but under the Design System's written 44px touch-target
floor. The two governing documents disagree with each other; put to the
client in §4j rather than picked unilaterally.

`ruff` clean; **245 tests pass** (3 new: the word-wrap regression tests).

### 2026-09-12 — Session 19: the htmx fragment-swap pass (§4i's last deferral closed)

**Decision, made while implementing rather than assumed beforehand**
- The original deferral (session 13) worried that htmx swaps would need
  server-side `HX-Request` branching — a route change outside this pass's
  "templates only" rule. Turned out not to be true: htmx already follows a
  redirect response itself, exactly like a browser does, before handing the
  final body to `hx-select`. So every mutating Till form keeps its existing
  `method="post" action="..."` (untouched fallback) and gains
  `hx-post="<same url>" hx-select="#till-body" hx-target="#till-body"
  hx-swap="outerHTML"`. The view function is never touched and cannot tell the
  difference. Recorded here because the original worry was wrong, not because
  the plan changed on request.

**Done**
- `templates/till/till.html` — `id="till-body"` wraps the cart + summary
  columns; every mutating form (add/scan, stepper ±, remove, set weight, set
  amount, clear, name-this-till, provisional-create) got the four `hx-*`
  attributes above. Checkout's form deliberately did **not** — it stays a real
  navigation to Sale Complete, a distinct "moment" (Design System's own
  reasoning, §10.3).
- Scan-field focus restored after every swap: `id="scan-input"` on the field,
  and a small script listens for `htmx:afterSwap` on `#till-body` and refocuses
  it — the same "cursor returns to the scan field" promise ADR-0011 §1 already
  made for bulk entry, now honoured for the Till too.
- **Verified in a real browser, not asserted.** Added `puppeteer-core` as a dev
  dependency (drives the system Chrome directly, no bundled browser download)
  and wrote three scripts against a live dev server:
  1. Add a sealed product, click "+" three times, remove the line — asserted
     `framenavigated` fired **zero** times across the whole sequence, the
     stepper's displayed quantity was correct at each step (1 → 4), and the
     scan field held focus and was cleared after every swap.
  2. Add a loose product (opens straight into the weight/amount Alpine control,
     per the §4b design), type a weight, submit — same zero-navigation proof,
     plus the row correctly collapsed to show "1.5 kg" and stopped needing a
     weight.
  3. A full cash checkout — confirmed this path still performs a **real**
     navigation to `/till/complete/<id>` with a "Sale complete" heading, proving
     the one deliberately-excluded form was not swept up by mistake.
- `ruff` clean; **242 tests pass, 95% coverage** — the Flask test client never
  executes JS, so the existing route-level test suite was unaffected by design;
  the interaction behaviour itself was proven by the puppeteer scripts above,
  not by pytest.

**Phase 3.5's §4i tracker is now fully closed.** One step remains before Phase 4:
the design-DoD side-by-side against all 9 reference screenshots.

### 2026-09-12 — Session 18: Phase 3.5 — the landing page (§4i tracker complete)

**Done (templates + `input.css` only — no route changes)**
- **`placeholder.html`** — considered and rejected redirecting an authenticated
  visit straight to the Till (the Design System has no separate "home" screen;
  the rail is the way in). Chose the smaller, safer move: restyle what exists
  rather than change `routes/main.py`'s behaviour, consistent with this pass's
  own rule. Authenticated: a "Welcome back, {name}" heading and three tile
  cards (Till/Stock/Refunds, each with its section's icon and tint colour) as a
  calmer alternative to the old bullet list. Anonymous: a plain "Sukoon" heading
  and a "Sign in" button — unchanged behaviour, just styled.
- Deliberately kept a literal, contiguous "Sukoon" text node on the page (not
  just inside spans split for the wordmark treatment) — the Phase 0 required
  smoke test (`test_app_boots_and_serves_placeholder`) greps the raw response
  body for `b"sukoon"`, and a split wordmark would have silently broken it.
  Ran the test rather than assumed.
- `ruff` clean; **242 tests pass, 95% coverage** — unchanged.

**Every screen in the §4i tracker is now converted.** Two items remain to close
Phase 3.5: the deferred htmx pass, and the final design-DoD side-by-side.

### 2026-09-12 — Session 17: Phase 3.5 — Refunds converted (resolves O-7's pixels)

**Done (templates + `input.css` only — routes/services untouched)**
- **`refunds/find.html`** — a search card (matches the Till/Stock scan-field
  pattern), the found sale as a summary row with a status pill and "Start a
  refund" CTA. Dropped a redundant inline "no sale found" message that
  duplicated the route's existing flash.
- **`refunds/sale.html`** — the refund-line table restyled (`panel`/`table`),
  status pills on both the sale and its existing refunds (amber
  `pending_approval`, teal `approved`, coral `rejected`/`out`, matching the
  Stock bar's colour vocabulary). Added a **live per-line refund-amount preview**
  (`≈ Rs …`, Alpine, client-side estimate only) that wasn't in the functional
  version at all — the cashier previously got no feedback on the refund amount
  before submitting. `refund_service` stays the only authority on the real figure.
- **`refunds/pending.html`** — each pending refund as a panel: total + method
  pill, reason, a sunk-background line-item breakdown with restock/damaged pills,
  the step-up password field and Approve/Reject actions.
- No reference screenshot exists for Refunds (O-7's design gap was always
  policy + data model, resolved at the Phase 3 gate — ADR-0020; the pixels were
  the remaining half). Built on the established card/panel/pill/field vocabulary
  per ADR-0006 rule 4, not a literal mock recreation.
- Verified with real screenshots: seeded a real sale and a real pending refund,
  walked find → sale → pending as both a Cashier and an Admin. No bugs found
  this round — the discipline from the last two sessions (screenshot before
  calling it done) held up with a clean pass.
- `ruff` clean; **242 tests pass, 95% coverage** — unchanged, confirming the
  templates-only rule held.

**Next:** `placeholder.html`, then the deferred htmx pass, then the full
design-DoD side-by-side (§4i) — the last items before Phase 4.

### 2026-09-12 — Session 16: Phase 3.5 — Stock converted (Figures 3, 7)

**Done (templates + `input.css` only — routes/services untouched)**
- **Stock list** (`stock/list.html`, Figure 3): the 4 stat cards (catalog size,
  stock value, needs attention, out of stock), the search/category/needs-completing
  filter row, Add product / Bulk entry / Categories actions, and a real **labelled
  stock-level bar** per row. The bar's fill is a display-only read of the same
  `compute_stock_status` result already computed — never a second source of truth:
  full/teal with no threshold set, scaled to 2x the threshold when one exists, and
  **always empty at zero stock regardless of threshold** (a real bug caught by
  screenshot review: the first version showed a full coral bar for an out-of-stock
  item with no threshold configured — an empty product looking "full" red is worse
  than no bar at all). Pure Jinja arithmetic, no Python touched.
- **Product detail** (`stock/product_detail.html`): stat-card info row, and the
  **Add Stock modal** (Figure 7) as a real `<dialog>` — the segmented Stock in /
  Stock out / Correct count control, a live "new stock level" preview (Alpine,
  echoing — not replacing — `apply_stock_movement`'s authoritative arithmetic on
  submit), barcode list/assign/label-sheet sections, movements table. Fixed a
  second real bug here: `class="capitalize"` on `stock_in` rendered "Stock_in"
  (CSS capitalize doesn't treat `_` as a word boundary) — now
  `.replace('_', ' ')` first, so "Stock in".
- **Product form, bulk entry, categories**: no reference screenshot for these
  (ADR-0006 rule 4 — the established `card`/`field`/`label`/`btn` vocabulary,
  applied consistently, not invented per screen).
- `input.css`: `.stat-card`/`.stat-label`/`.stat-value`/`.stat-sub`,
  `.stock-bar-track`/`.stock-bar-fill`, and `dialog.modal` (+ `::backdrop`,
  Design System §4.5 — Surface white, 26px radius, ink at 40% opacity). Checkboxes
  across Stock get `accent-teal` for brand consistency (a native-control detail
  noticed in the categories screenshot).
- Verified with real headless-Chrome screenshots at every step, including forcing
  the `<dialog open>` attribute to inspect the modal's contents without scripting a
  real click. One tooling detour worth recording: an early screenshot round
  silently rendered fully unstyled — not a CSS bug, but Chrome's `ERR_UNSAFE_PORT`
  silently blocking the dev server's port (5060, one of Chrome's blocklisted
  ports); moving to a different port fixed it.
- `ruff` clean; **242 tests pass, 95% coverage** — unchanged, confirming the
  templates-only rule held.

**Next:** Refunds (O-7 pixels), §4i.

### 2026-09-12 — Session 15: till terminal identification (ADR-0023)

**Decision**
- Client asked for "multiple tills." Put to them as a scoped question since it
  touches the long-open **O-8** and the architecture already supports concurrent
  terminals by design (ADR-0001 LAN/browser model; Phase 3's atomic invoice
  numbering and guarded stock updates already proven safe under real concurrency).
  They chose the narrowest option: **identify which till rang up each sale.**
  [ADR-0023](adr/0023-till-terminal-identification.md) — a till's name lives in a
  long-lived cookie (a property of the physical PC/browser, not of whoever is
  logged in — rejected asking at login, and rejected server-side config since one
  Flask process serves every terminal). Resolves O-8's labelling half; live
  registration/health-status stays open, explicitly not built.

**Done (real routes + service wiring — outside Phase 3.5's templates-only rule,
by design, since this is a Phase 3 functional addendum, not a restyle)**
- `routes/till.py` — `_terminal_label()` reads the `sukoon_terminal` cookie;
  `POST /till/terminal` sets/renames it (a blank label is ignored, never
  overwrites); `index()` and `checkout()` thread it through.
  `sales_service.record_sale(terminal_label=...)` has accepted this since Phase 1
  (`sale.terminal_label`, frozen, always `NULL` until today) — no migration.
- `services/receipts/receipt.py` — `ReceiptData.terminal_label`; `build_receipt`
  copies it from the sale; `receipt_body` shows a "Till" row when present — one
  change, both the ESC/POS and PDF renderers pick it up since they share the
  layout.
- `templates/till/till.html` — a one-time "Name this till" card when unset;
  once set, a small pill + inline rename (Alpine `x-data`), consistent with the
  loose-row pill pattern from session 14.
- `templates/till/complete.html` — the till's name appended to the invoice line.
- Verified visually (screenshot before and after naming) — caught and fixed a
  real icon collision this way: the till pill first reused the Stock rail's box
  icon, confusing at a glance; swapped for a monitor icon.
- `tests/integration/test_till.py` (+6), `test_receipts.py` (+1). `ruff` clean;
  **242 tests pass, 95% coverage**.

**Open / next:** back to Phase 3.5 — Stock is next (§4i).

### 2026-09-11 — Session 14: Phase 3.5 — Till + Sale Complete converted

**Done (templates + `input.css` only — no route or service changes)**
- **Till (`till/till.html`, Figure 2):** two-column layout — scan field, cart
  cards, summary/payment panel — against the prototype's literal spacing/shadow
  values. Sealed-pack rows keep the stepper untouched. Loose rows implement the
  §4b design exactly: a fresh/unweighed line opens by default in the amber
  "needs weight" state with the segmented **Weight (kg) / Amount (Rs)** toggle
  (Alpine `x-data` per row — `mode`, and `weight`/`amount` with `get approxRs()`
  / `get approxKg()` computed getters for the live `≈` preview); once set, the
  row collapses to a compact value pill, tap to reopen. Payment is three
  equal-weight pills with an Alpine active state; cash mode adds the
  received-amount field, Exact/round-number quick buttons, and a live "change to
  return" preview — all client-side convenience over the same server-authoritative
  total, nothing here changes what gets submitted or how `checkout` computes.
- **Sale Complete (`till/complete.html`, Figure 8):** full-bleed radial wash,
  checkmark, change figure, and the **real O-9 auto-advance ring** — an Alpine
  countdown (`seconds`, `cancelled`, a 1s `setInterval`) draining an SVG ring
  around "Start next sale" over 8 seconds, cancelled by any keypress or click
  and by interacting with the receipt buttons; a `<noscript>` meta-refresh is
  the no-JS fallback. Receipt outcome shown as a pill (printed / printer
  unavailable) with PDF and "print again" actions.
- `[x-cloak] { display: none !important; }` added to `input.css` (Alpine-hidden
  elements no longer flash visible before Alpine mounts).
- **Verified visually, not just by markup review:** built a real cart (sealed +
  two loose lines, one left deliberately unweighed) against the actual dev
  server via a small script (login, add-to-cart, set-weight over HTTP), and
  took real headless-Chrome screenshots of both the Till (mid-flow, showing the
  needs-weight and filled loose states together) and Sale Complete. Both sent
  to the client. Caught and fixed one real bug this way: the countdown ring's
  `stroke-dashoffset` formula had time backwards (filling instead of draining) —
  wrong on markup review alone, visible immediately once rendered.
- `ruff` clean; **235 tests still pass** — confirms the "templates only" rule
  held (no Python behaviour touched this session).

**Deliberately deferred (recorded in §4i, not silently skipped):** true htmx
fragment-swapping for cart mutations (Design System §10.3). Alpine covers the
client-side polish instead; the swap pass needs route-level response handling
and real browser interaction testing, so it's split out as its own step.

### 2026-09-11 — Session 13: Phase 3 signed off; Phase 3.5 visual pass — toolchain + shell + Login

**Sign-off**
- **Client approved the Phase 3 functional DoD (§4h)** and directed that the
  ADR-0022 visual pass begin. Phase 3 (POS & Billing) is functionally complete.

**Done (Phase 3.5 — templates & static assets only, no route/service changes)**
- **Front-end toolchain** (build-time only; `node_modules/` gitignored):
  `package.json` (`tailwindcss`, `alpinejs`, `htmx.org`, `@fontsource/inter` as
  dev deps), `tailwind.config.js` (Design System §10.2 token palette + the
  prototype's literal radius/shadow values — ADR-0006), `sukoon/static/css/input.css`
  with an `@layer components` layer, `scripts/build_css.sh` + `npm run build:css`.
  The **compiled `sukoon/static/css/tailwind.css` is committed** (Dev Spec §5.1 —
  no Node ships in the installer).
- **Assets bundled locally, no CDN** (Design System §10.1): Inter 400–800 Latin
  subset as **woff2** in `static/fonts/` (closes the §4 woff-vs-woff2 issue);
  Alpine 3 + htmx 1.9 vendored to `static/js/`.
- **`base.html`** rebuilt as the real app shell — a persistent 78px nav rail
  (Till / Stock / Refunds + sign-out) and a 72px top bar with the user chip
  (Design System §5). Full-bleed "moment" screens (Login, Sale Complete) opt out.
- **Login (Figure 1)** converted: radial calm-wash background, staff avatar row
  (route now passes active users + a time-of-day greeting), Alpine avatar→password
  reveal (`x-data`/`x-show`/`x-transition`, §10.4), "or type your name" fallback.
  The ADR-0008 password-for-PIN deviation is kept and re-noted in the template.
- `ruff` clean; **235 tests pass** (unchanged — this session changed no Python
  behaviour, only `routes/auth.py`'s render context and templates).

**Next:** §4i tracker — Till + Sale Complete, then Stock, then Refunds.

### 2026-09-11 — Session 12: ESC/POS receipts + PDF fallback — Phase 3 functionally complete

**Done**
- `services/receipts/receipt.py` (no Flask) — `ReceiptData` + `build_receipt(sale)`
  (shop name/contact from `setting`, defaults to "Al-Rehman General Store"),
  `receipt_body` (one aligned-text layout both renderers share, so the printed and
  PDF receipts say the same thing), `render_escpos` (ESC/POS bytes via a Dummy
  device — pure), `render_pdf` (80 mm ReportLab roll).
- `services/receipts/printer.py` — printer config from `setting`
  (`receipt.printer.kind` none|network|usb|serial|file, host/port/timeout/…);
  `send(bytes)` raises `PrinterUnavailable` for every failure mode (no printer,
  bad address, refused, missing backend, timeout).
- `services/receipts/service.py` — `issue_receipt(sale) -> ReceiptOutcome`: tries
  the printer, falls back to "offer the PDF" on any problem, **never raises**
  (it runs after the sale commits — ADR-0003 §6). `receipt_pdf(sale)` serves the
  PDF on demand, nothing stored.
- `routes/till.py` — `checkout` calls `issue_receipt` post-commit; `complete`
  shows the outcome + a PDF link + "Print again"; `GET /till/receipt/<id>.pdf`,
  `POST /till/receipt/<id>/reprint`.
- Dep: `python-escpos==3.1` (requirements.txt, Phase 3 section).
- `tests/integration/test_receipts.py` — 15 tests (content, ESC/POS bytes, PDF,
  the printer decision incl. an unreachable network printer and a working `file`
  printer, never-raises, and the till route). `ruff` clean; **235 tests pass,
  95% coverage**.

**Phase 3 is functionally complete.** DoD presented in §4h, awaiting client
sign-off. Next: ADR-0022 Phase 3.5 visual pass.

### 2026-09-11 — Session 11: the refund flow (ADR-0020)

**Done**
- **`models/refund.py`** — `Refund` (sale_id, total_paisa, method
  cash|credit_ledger|card, reason non-blank CHECK, status, initiated_by /
  approved_by, resolved_at) and `RefundItem` (sale_item_id, quantity_milli > 0,
  line_total_paisa, `restock` default true). Registered in `models/__init__`.
- **Migration `58f3a01f76d8`** — the first since the Phase 1 freeze. Autogenerated,
  reviewed, up→down→up verified through the real `flask db` CLI. `test_migration`'s
  expected-table set updated.
- **`services/refund_service.py`** (no Flask):
  - `refundable_quantity_milli` — sold minus approved *and* pending (a pending
    refund reserves its quantity).
  - `initiate_refund` — validates every line (belongs to the sale, > 0, ≤
    refundable; a `manual_amount` line is whole-or-nothing and refunds its exact
    `line_total_paisa` per ADR-0007; others round half-up at the line), writes a
    `pending_approval` `Refund` + items, **moves nothing**.
  - `approve_refund` — one transaction: `apply_stock_movement('refund',
    commit=False)` for each line with `restock` (skips damaged), a negative
    `credit_ledger_entry` + balance update for a credit sale, `refund.status =
    approved`, and `sale.status` → `partially_refunded` / `refunded`. A failure
    rolls it all back and the refund stays pending (tested with a monkeypatched
    failure).
  - `reject_refund`, `list_pending`, `refunds_for_sale`.
- **`routes/refunds.py`** + `templates/refunds/` — `/refunds/find` (by invoice),
  `/refunds/sale/<id>` (the initiate form, per-line qty + restock + reason),
  `/refunds` POST (`sale.refund_initiate`), `/refunds/pending`, approve
  (`sale.refund` + `require_step_up`), reject. Blueprint registered; "Refunds"
  in the header.
- `tests/integration/test_refunds.py` — 20 tests. `ruff` clean; **219 tests pass,
  95% coverage** (refund_service 98%).

**Open (last Phase 3 piece)**
- ESC/POS receipt + PDF fallback (`services/receipts/`).

### 2026-09-11 — Session 10 (cont.): visual-pass scheduling decided

- **[ADR-0022](adr/0022-dedicated-visual-pass.md) Accepted.** Dev Spec §5.1 says
  style-as-you-go with no separate phase; Phases 1–3 deviated (functional HTML).
  Client decided: finish Phase 3 functional, then **one dedicated visual pass
  ("Phase 3.5")** converts every template to the Design System and compiles
  `tailwind.css`, before Phase 4. The design DoD for Phases 1–3 is met at the
  close of that pass. Recorded in §4b.

### 2026-09-11 — Session 10: the Till (cart, payment, Sale Complete)

**Done**
- `routes/till.py` (`/till`, thin per ADR-0003 §2) — the cart lives in the signed
  session; the route marshals session rows ↔ `sales_service.CartLine` and renders.
  - `add` — resolves a scan/typed fragment via `inv.resolve_barcode` then a unique
    name/SKU match; sealed pack → one row per product, stepper bumps on re-add;
    loose → a fresh row with **no quantity** ("needs weight").
  - `update_line` — stepper inc/dec (drops the row at zero), `set_weight`,
    `set_amount` (whole rupees; weight derived via `pricing.compute_quantity_from_amount`),
    `remove`.
  - `checkout` — blocks an empty or unweighed cart, calls `record_sale`, clears the
    cart, redirects to Sale Complete. `SaleError` / `InventoryError` → flash.
  - `complete` — the invoice, change, and line items.
- `sales_service.summarize_cart` — pure; line totals + subtotal + `ready` (false
  while any loose line is unweighed) + `unweighed_count`. `CartLine.quantity_milli`
  is now `int | None`.
- `templates/till/till.html`, `till/complete.html` — functional HTML (§4b Phase 3
  UI deviations). Sale Complete uses an 8-second `meta refresh` as the O-9 ring's
  stand-in.
- Till blueprint registered; "Till" added to the header and the landing page.
- `tests/integration/test_till.py` — 23 tests (cart building, stepper, loose
  needs-weight + blocked checkout, by-weight / by-amount entry, barcode & name
  resolution, cash / card / credit checkout, insufficient-stock block, the
  complete page).
- `ruff` clean; **199 tests pass, 95% coverage** (till.py 91%).

**Then (same session)**
- **Provisional-create at the till** (ADR-0011 §2 / O-16): an unknown scanned code
  offers inline creation for anyone with `product.create_provisional` (Cashier
  included) — `POST /till/new`, name + price only so it is always provisional,
  barcode assigned, dropped in the cart, listed under "Needs completing". 3 tests.

**Deferred (Phase 3, still open)**
- The `refund` / `refund_item` migration + refund service (ADR-0020).
- ESC/POS receipt + PDF fallback (`services/receipts/`).

### 2026-09-11 — Session 9: Phase 3 sale-transaction core

**Done (build — services only, no routes/UI yet)**
- `services/invoicing.py` — **pure** (ADR-0003 §3): `format_invoice_number`, and
  `compute_next_counter` (the yearly-reset arithmetic — same year advances, new
  year resets to 1; a quiet year still rolls over on its first sale).
- `services/pricing.py` — **pure**: `compute_line_total_from_quantity` (delegates
  to `money`), `compute_quantity_from_amount` (weight from a typed amount),
  `line_total_paisa_for` (manual_amount → the typed rupees, authoritative),
  `cart_subtotal_paisa`.
- `services/sales_service.py`:
  - `claim_invoice_number` — one atomic `UPDATE invoice_counter … RETURNING` with
    a `CASE` for the year reset. Race-safe: verified by a 50-thread on-disk WAL
    test, no duplicates, no gaps. Does not commit (the caller owns the txn).
  - `record_sale` — sale + `sale_item` rows + per-line stock deduction +
    (credit only) a `credit_sale` ledger entry and balance update, all in **one**
    commit. Guards: empty cart, unknown payment method / quantity source, zero
    quantity, sealed-pack fractional or by-amount, non-whole-rupee typed amount,
    cash tendered < total, credit with a missing customer. A failure anywhere
    rolls the whole thing back **including the claimed invoice number** (tested).
- `inventory_service.apply_stock_movement`:
  - new `commit=False` so `sales_service` folds deductions into the sale txn.
  - the in/out/sale/refund path is now a single **guarded relative**
    `UPDATE … RETURNING` (`WHERE stock + delta >= 0`) — no more read-in-Python
    then write-absolute, so concurrent sales of one product can't lose an update
    (tested, 30 threads). `correction` still writes an absolute level (rare manual
    action — noted).
- `app.py` — `PRAGMA busy_timeout=5000`; `create_app(config_overrides=...)` for
  the on-disk concurrency fixture.
- `seed.py` — `seed_invoice_counter()` (reference data, always run by `seed_all`).
- `ruff` clean; **176 tests pass, 95% coverage** (sales_service 100%).

**Decisions**
- [ADR-0021](adr/0021-invoicing-module-purity.md) (Accepted) — ADR-0003's module
  list said `invoicing.py` is "pure … + atomic allocation", self-contradictory
  (pure = no I/O). Rule 3 wins: `invoicing.py` stays pure, the atomic DB claim
  lives in `sales_service.claim_invoice_number`.
- **Credit-limit enforcement (ADR-0014) is not in `record_sale`** — it's Phase 4.
  A credit sale currently posts to the ledger with no limit check.

**Open / next**
- The Till routes + templates (`routes/till.py`) — cart state, scan/search →
  cart, the loose-goods row (§4b design), payment wired to `record_sale`, Sale
  Complete with the auto-advance ring. Then the `refund` migration + service
  (ADR-0020), then receipts.

### 2026-09-11 — Session 8: Phase 3 gate closed; money helpers; Till design (O-11, O-9)

**The gate (§4g)**
- Put the four Phase 3 gate questions to the client (discounts, refund authority,
  refund mechanics, `catalog.manage`/`stock.adjust`). Answers recorded in §4g and
  in [ADR-0020](adr/0020-phase-3-refund-and-discount-policy.md), written and Accepted.
- **Discounts:** confirmed none in v1 — no build.
- **Refunds:** Cashier initiates → Admin approves with step-up. Original invoice
  required, partial refunds allowed, auto-restock (+ per-line damaged flag),
  credit-sale refunds reverse the ledger. This **refines ADR-0008 §4** (was
  "Admin only") — recorded, not silently overridden. Resolves **O-7** (policy +
  data model; the screen's pixels stay deferred with the rest of the UI).
- **New schema:** `refund` + `refund_item` tables → a **new migration** in Phase 3,
  the first since the Phase 1 freeze. Shape proposed in ADR-0020 for the client's
  review; Phase 3's DoD is the checkpoint, not a further gate.
- **`catalog.manage` / `stock.adjust`:** stay coarse, Admin-only, no step-up.
  Closes the ADR-0019 open item.

**Done (build)**
- `services/money.py` — the ADR-0007 rupee-boundary rule in one pure place:
  `round_paisa_to_rupee` (half-up, symmetric about zero so a refund mirrors its
  sale), `is_whole_rupee`, `line_total_for_quantity` (single half-up step, no
  intermediate paisa rounding). No Flask, no DB.
- `tests/pure/test_money.py` — the ADR-0007 boundary matrix (0/1/49/50/51/99/100/
  149/150), negative symmetry, "output is always a whole rupee" over a range, and
  line-total rounding. 29 new tests.
- `services/permissions.py` — `sale.refund_initiate` added (Cashier + Admin);
  `sale.refund` description clarified to "approve or reject". Seed is dict-driven,
  no seed code change; `flask seed` picks it up.
- `ruff` clean; **140 tests pass; 95% coverage** (money.py 100%).

**Done (design)**
- Resolved **O-11** and **O-9** with the client (four interaction questions), then
  mocked them up matching the prototype's exact CSS values. Working files in
  `docs/design/drafts/till-fractional-cart/` (`Main` / `LooseRow` / `SaleComplete`
  `.dc.html` + `canvas.json`), published as an Artifact.
- **O-11:** inline-expanding loose-goods row — two-segment Weight/Amount toggle, one
  input, live `≈` preview, amber "needs weight" state that blocks checkout. §4b.
- **O-9:** ~8s cancellable auto-advance ring on "Start next sale". §4b.

**Open / next**
- Phase 3 build. Till UI now unblocked. Build order in §1 Next action.
- Design-independent first steps: atomic race-safe invoice numbering
  (`invoice_counter`, yearly reset per ADR-0016), sale + stock-deduction in one
  transaction, then the `refund`/`refund_item` migration + refund service (ADR-0020).
- Non-blocking carryovers: O-8, O-10, O-12, O-18, O-20. LICENSE owner-name
  placeholder still open.

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
