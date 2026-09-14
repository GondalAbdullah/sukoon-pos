# Phase 5 — WhatsApp Notifications: Proposal for the grill session

Status: **GRILLED 2026-09-14 (session 25) — superseded by [ADR-0027](../adr/0027-whatsapp-provider-and-account.md) to [ADR-0033](../adr/0033-whatsapp-operational-safety.md).** Kept unedited below as the starting point; where it differs from those ADRs, the ADRs win. Originally: **PROPOSAL — nothing here is decided.** Written 2026-09-14 (session 24) as the
artefact for the `grill-with-docs` session the Development Specification requires
before any Phase 5 code (Phase 5 step 1; the 🛑 gate "confirm the provider, message
template wording, and retry/backoff limits before implementation"). Per the spec's
operating rule 10, each open decision carries a **recommendation with reasoning**;
the grill exists to attack those recommendations, and only what survives becomes an
Accepted ADR.

Facts marked **(verify)** are things I believe but have not confirmed against a
current source — prices, limits and platform rules change. Check each one during the
session rather than building on it.

---

## 1. What Phase 5 must deliver (Development Specification)

- A provider-agnostic adapter, so the WhatsApp vendor can change without touching
  business logic.
- An async queue (APScheduler, in-process) that a credit sale enqueues into instead of
  calling the provider inline.
- Retry with capped, backed-off attempts, then a **visible** failure log.
- Messages: a credit-sale notice (items, amount, previous and new balance); monthly
  statement delivery. ADR-0015 adds overdue reminders.
- Required tests: mocked-provider success / failure / retry cap; a sale completes with
  the provider disabled or unreachable; no duplicate send for one event; statement
  generation correct across month and timezone boundaries.
- **Hard gate in the DoD:** the sale flow is verified unaffected by provider downtime.

## 2. Already settled — the grill should not reopen these without cause

| Source | What it fixes |
|---|---|
| ADR-0001 | WhatsApp is the **only** part of Sukoon allowed to need the internet; APScheduler in-process; no broker daemon. |
| ADR-0003 §6 | A secondary action never breaks a primary one — enqueueing can't raise into a sale. Layout: `services/notifications/{queue.py, providers/}`, `jobs/`. |
| ADR-0016 | `notification_queue` exists: `notification_type` (`credit_sale` / `statement` / `overdue_reminder`), **UNIQUE `dedupe_key`**, `payload_json`, `status` (`pending` / `sent` / `failed` / `abandoned`), attempt count and timestamps, `last_error`. |
| ADR-0013 §4 | **An unconfirmed number never receives money details** — only a neutral "an account was opened in your name" notice. §5: OTP deferred (O-18). |
| ADR-0015 | Overdue accounts get reminders through the same queue, **confirmed numbers only**; a separate sweep job, "daily" as the working assumption. |
| ADR-0024 | Month boundaries are the shop's calendar (Asia/Karachi). |
| ADR-0026 | The statement document and its A4 PDF already exist (`services/statements.py`). |

## 3. Decisions for the grill

### D1 — The provider

| Option | For | Against |
|---|---|---|
| **A. Meta WhatsApp Business Cloud API, direct** *(recommended)* | Official; no middleman markup; templates, media and delivery status are first-class; nothing to host. | Setup burden: a Meta Business account, a phone number dedicated to the API, template approval, and billing on a card **(verify current requirements)**. |
| B. A Business Solution Provider (Twilio, 360dialog, Gupshup, Infobip…) | Easier onboarding and support; some bill locally. | A markup on every message; one more company that can change terms; still Meta's templates underneath. |
| C. Unofficial WhatsApp Web automation (whatsapp-web.js, Baileys…) | No approval, no per-message fee. | **Recommend rejecting outright.** Against WhatsApp's terms; the shop's number can be banned; needs a logged-in phone session that silently expires — exactly the "provider lying" failure the spec is written against, and it would be the shop's personal number at risk. |

**Why A:** the adapter interface means B stays a drop-in if onboarding with Meta proves
too hard, so choosing A costs nothing irreversible.

**Questions only the client can answer:** Does the shop have (or want) a Meta Business
account in **the owner's** name, not the developer's? Is there a phone number that can
be dedicated to it (a number registered to the API generally can't also be used in
the normal WhatsApp app at the same time **(verify)**)? Who pays the Meta bill?

### D2 — What each message says (templates)

Business-initiated WhatsApp messages must use **pre-approved templates** with variables
**(verify: utility category, approval turnaround)**. Proposed drafts, English — **the
client decides the language** (English, Urdu script, Roman Urdu, or two templates):

- **Credit sale** (confirmed number): *"Al-Rehman General Store: {{items}} — Rs {{amount}}
  added to your Khata on {{date}}. Previous balance Rs {{previous}}, now Rs {{new}}."*
  Open question: a long bill won't fit — propose the first 3 items then "and N more"
  **(verify template body length limit)**.
- **Monthly statement** (confirmed number): a short text plus the existing A4 PDF as a
  document attachment — *"Your Khata statement for {{month}}: closing balance
  {{closing}}."* In-credit wording must never read as a negative (ADR-0026 §7).
- **Overdue reminder** (confirmed number): *"A gentle reminder: Rs {{balance}} is due on
  your Khata at Al-Rehman General Store. Thank you."* — tone matters; the Design System's
  copy rules (no blame, no exclamation marks) should apply to customers too.
- **Neutral notice** (unconfirmed number, ADR-0013 §4): *"An account has been opened in
  the name of {{name}} at Al-Rehman General Store. If this is not you, please contact
  us."* No amounts, ever.

**Recommend:** every money message states **"as of {{time}}"** — a message delayed by a
dead internet connection must not present an old balance as current (see D3).

### D3 — Retry and give-up policy

**Recommend:**
- Backoff after a failed attempt: 1 min, 5 min, 30 min, 2 h, 6 h — **5 attempts**, then
  `failed`, visible on screen (D9).
- **Also give up by age**, whatever the attempt count: a credit-sale notice older than
  **48 hours** becomes `abandoned` — "Rs 600 added, now Rs 9,750" arriving three days
  late, after a payment, is worse than nothing. Statements: 7 days. Reminders: 24 hours
  (tomorrow's sweep will make a fresh one).
- **Permanent errors skip the retries**: not a WhatsApp number, template rejected,
  number malformed → `abandoned` at once with the reason. Only network errors, timeouts,
  rate limiting and server errors retry.
- **The unasked question:** when the shop's internet is down all afternoon, should
  connection failures burn attempts? Recommend **no** — a connectivity failure
  reschedules without counting; the age limit still ends it. Otherwise one outage turns
  every message of the day into `failed`.

### D4 — What "sent" means

Meta reports delivery and read status through **webhooks**: Meta calls a public HTTPS
address. The shop PC is on a LAN with no public address (ADR-0001), so webhooks would
need a tunnel or a relay service — new infrastructure and a new internet dependency.

**Recommend for v1:** "sent" means **the API accepted the message**; no webhooks. The
cost, stated plainly: a message Meta accepted but couldn't deliver (phone off for weeks,
number no longer on WhatsApp) looks sent. **Trigger to revisit:** the client reports
customers saying they never received messages.

### D5 — Where the access token lives

A long-lived API token on the shop PC is a secret that can send messages as the shop
(`Building-Software-The-Right-Way`: secret handling).

**Recommend:** not in the database (it's backed up and copied around) and never in the
repo. Keep it in a local config file outside the install folder with Windows
per-user file permissions, or protected with Windows DPAPI **(verify what PyInstaller +
the chosen service account make practical — overlaps Phase 7's grill)**. Admin-only
screen to set or replace it, never to display it.

### D6 — Consent

WhatsApp's business policy requires customers to **opt in** to business-initiated
messages **(verify current wording)**. Nothing in the schema records consent today.

**Recommend:** a tick on "Open a Khata" — *"Send updates on WhatsApp"* — stored as a
new column (e.g. `customer.whatsapp_opt_in` + when + by whom). **This is a migration,
so it's expensive to reverse and deserves the hardest questions.** No opt-in → nothing
is queued for that customer, including the neutral notice? (Grill question: the neutral
notice exists to catch a *wrong* number; does it need consent from the person who may
not be the customer?) Opting out in v1: the shop unticks it on request; automatic
"STOP" handling needs webhooks (D4).

### D7 — Monthly statements: when, and if the PC is off

APScheduler in-process only runs **while Sukoon is running**. A shop PC switched off on
the 1st would silently skip the month.

**Recommend:** a job at **09:00 shop time on the 1st** for the previous month, plus a
**catch-up on start-up** that sends any month not yet done. The dedupe key
`statement:{customer_id}:{YYYY-MM}` makes re-running harmless. Who gets one: confirmed,
opted-in numbers with a non-zero closing balance **or** any activity that month.
Grill question: a settled customer with no activity — send nothing (recommended)?

### D8 — Overdue reminders: how often (and O-20)

A daily sweep that messages every overdue customer daily is spam.

**Recommend:** at most **one reminder per customer per 7 days**
(`overdue:{customer_id}:{ISO week}`), and **O-20's collision rule:** skip the reminder if
that customer was sent a statement in the last 3 days — the statement already shows the
balance. Sweep at 11:00 shop time.

### D9 — Where people see messages

**Recommend** an Admin-only **Messages** screen: pending / sent / failed / abandoned with
the reason in plain words, a **Retry now** for failed ones, and a count this month
(for the Meta bill). The Khata screen gains the mock's banner ("A WhatsApp update was
sent after the last credit sale") and **Send reminder** (same dedupe, so a double-click
can't send two).

### D10 — One scheduler, exactly once

If two Sukoon processes ever run (a second launch, a future multi-worker server), each
would start APScheduler and both would process the queue. **Recommend:** the queue
worker **claims** a row with an atomic conditional update (the same pattern as the
invoice counter and stock guard) before sending, so two workers can't send one message;
the UNIQUE `dedupe_key` stops double *enqueueing*. Tested with threads, like Phase 3's
concurrency tests.

## 4. Proposed out of scope for v1 (say so plainly, or bring it in deliberately)

SMS fallback · inbound replies or chat · marketing or promotional messages ·
delivery/read receipts (D4) · OTP number verification (O-18 — its trigger *is* Phase 5
completing, so raise it at the end, don't build it now) · messages to walk-in
customers.

## 5. After the grill, the build (not before)

1. ADRs for D1–D10 as decided. 2. `providers/` interface + a fake provider + the chosen
real adapter. 3. `queue.py`: enqueue (never raises into a sale), claim, send, retry,
give up. 4. `jobs/`: queue worker, monthly statements with catch-up, overdue sweep.
5. Templates. 6. Messages screen, Khata banner and Send reminder. 7. The required tests,
with the provider down as a hard gate. 8. One real send through a sandbox or test
number, if the client's account exists by then.
