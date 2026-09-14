# 0033 — WhatsApp Operational Safety: Key, Switch, Daily Cap, Visibility, and Exactly-Once Sending

Status: **Accepted** 2026-09-14 — Phase 5 grill session
Date: 2026-09-14
Phase: 5
Grilled from: [docs/proposals/phase-5-notifications.md](../proposals/phase-5-notifications.md) §D5, §D9, §D10, plus two questions the proposal hadn't raised (a spending fuse; a crash mid-send)
Depends on: [ADR-0008](0008-authentication-and-access-control.md), [ADR-0016](0016-consolidated-data-model.md), [ADR-0027](0027-whatsapp-provider-and-account.md) (the owner controls everything after handover), [ADR-0028](0028-whatsapp-consent-and-eligibility.md) … [ADR-0032](0032-payment-receipt-message.md)
Defers to: the Phase 7 packaging grill for the exact Windows account the key is bound to

## Context

Everything so far decides *what* is sent and *when*. This ADR decides how the sending
machinery stays safe when people, bugs and power cuts get involved:

- **A secret.** A long-lived Meta access key can send messages as the shop, billed to the
  owner's card. The database is backed up and copied around; anyone at the PC can open
  files.
- **A bill with no ceiling.** A queueing bug, a restored backup re-triggering statements,
  or a hole in dedupe could send hundreds of charged messages before anyone notices.
- **Go-live.** The shop may run Sukoon for months before the Meta account is approved.
- **Two copies of Sukoon** (a double-clicked icon, a crashed window still running) would
  each start a message worker.
- **A crash mid-send** leaves a message whose fate is unknown: Meta may or may not have
  accepted it, and Sukoon can't ask afterwards **(verify)**.

## Decision

### The access key
1. **An Admin pastes the key once, inside Sukoon.** It is stored **encrypted with Windows
   DPAPI** in a file outside the database: backups never contain it, and the file is
   useless copied to another PC. The screen never shows it again — only "Key set on
   {date} · Replace". On the Linux development machine a file readable only by its owner
   stands in for DPAPI. Which Windows account the protection binds to is settled in the
   Phase 7 packaging grill.
   *Recorded honestly:* the grill's first answer was a developer-edited config file. It
   was reversed when the grill named the conflict with ADR-0027 — a key only the developer
   can replace leaves WhatsApp paused whenever the developer is unavailable after handover.

### The on/off switch
2. **WhatsApp sending starts off.** An Admin can switch it on only when the key and
   `whatsapp.reply_to_number` (ADR-0030) are both set.
3. **Off means nothing is queued** — Sukoon behaves as if WhatsApp doesn't exist, and
   switching on starts fresh from that moment. Switching off cancels pending messages as
   `abandoned` ("sending switched off"). **Off is not paused:** paused (ADR-0029, and the cap
   below) keeps queueing because the shop means to be sending.

### The daily cap
4. **A daily cap on messages sent**, setting `whatsapp.daily_cap`, **default 200**, counted
   per shop-time day. Reaching it **pauses** sending exactly as ADR-0029 does — same Admin
   banner: "Daily message limit reached: 200. Sending resumes tomorrow, or an Admin can
   raise the limit." Nothing is lost; age limits still apply.

### Who sees what
5. **An Admin-only Messages screen:** every message with its status and plain reason,
   **Retry now** for failed ones, **Send again** for outcome-unknown ones, this month's
   count, the switch, the key, and the cap. A new permission, **`whatsapp.manage`**
   (Admin).
6. **On each Khata, all staff see one line:** the last message and its state — "Last
   WhatsApp update: payment receipt, sent 14 Sep, 8:26 PM" or "Not sent: number not
   confirmed" — so the counter can answer "did you message me?".

### Exactly once
7. **Only one copy of Sukoon runs the message worker**, the one holding a lock file; a
   second copy serves screens and sends nothing.
8. **And, independently of the lock,** every send is claimed by one atomic update —
   `status 'pending' → 'sending' WHERE still pending` — and the daily count is incremented
   by one atomic `WHERE sent < cap`, the same pattern that already protects invoice numbers
   and stock. The lock prevents wasted work; the atomic updates make double-sending and
   cap overshoot impossible even if the lock is wrong. Tested with threads, like Phase 3.
9. **A message stuck in `sending` for 10 minutes is never resent automatically.** It
   becomes `abandoned` — "outcome unknown: Sukoon stopped while sending" — and the Admin can
   press **Send again** if the customer says they didn't receive it. A lost message is
   visible and fixable; a duplicate money message can't be taken back.

### Proving it works before go-live
10. **Send test message** on the Messages screen (Admin): type a number, press send. It
    sends the **account notice** template filled with the shop's own details as a sample,
    **bypassing consent and confirmation** (the recipient is not a customer), **counts
    toward the daily cap**, is recorded in the log as a test, and shows the real outcome in
    plain words — "Sent", "Key rejected", "Template not approved yet". **It works while
    sending is switched off**, so the owner can test before going live and again after
    replacing a key. This is the Development Specification's "manually trigger one real
    send".

### Schema added in Phase 5 (one migration, with ADR-0028's consent columns)
```
notification_queue.status   gains 'sending'           -- Python enum; no DB constraint exists
message_daily_count
  day         TEXT PK     -- shop-time date, YYYY-MM-DD
  sent        INTEGER NOT NULL DEFAULT 0
statement_run
  month       TEXT PK     -- YYYY-MM
  queued_at   DATETIME NULL
  skipped_at  DATETIME NULL   -- catch-up window missed (ADR-0031)
setting rows: whatsapp.enabled, whatsapp.daily_cap, whatsapp.reply_to_number,
              whatsapp.paused_since, whatsapp.paused_reason
```
The key itself is **not** in the schema.

## Alternatives Considered

- **Key in the database settings.** Simplest. Lost: every backup would carry a key that
  bills the owner's card.
- **A developer-edited config file** — first chosen, then reversed (see Decision 1).
- **Config file the owner can replace from a handover note.** Kept ADR-0027 intact with
  less to build. Lost when the client chose the encrypted, in-app route instead.
- **Warn-only cap, or no cap.** No legitimate message ever held back. Lost: the bill is
  unprotected against the one failure nobody tests for.
- **Queue while off; or ask on switching on.** Nothing missed while off. Lost: a burst of
  old messages at go-live, for a shop that wasn't yet messaging anyone.
- **Admin-only visibility everywhere / full log for all staff.** Lost: the first leaves
  cashiers unable to answer a customer; the second shows every cashier every customer's
  message history.
- **Atomic claim only / lock only.** Lost: claim-only is fine but wastes contention;
  lock-only has nothing behind it when a stale lock file or antivirus gets in the way.
- **Test through a real customer record** (a fake Khata and a Rs 1 credit sale), or **a
  command-line test only**. Lost: the first leaves fake records in the shop's books; the
  second means the owner can't re-test after replacing a key.
- **Retry an unknown send; or retry only non-money kinds.** Nothing lost. Lost: a crash at
  the wrong moment could tell a customer they were charged, or paid, twice.

## Consequences

- **Easier:** go-live is a switch; a bug can cost at most one day's cap; restarts,
  double launches and power cuts can't duplicate a message.
- **Harder:** DPAPI needs a Windows-specific code path and its Linux stand-in, both
  tested; the worker has three kinds of pause/stop to report (off, paused, cap).
- **Accepted:** after a crash mid-send, a customer may occasionally miss one message until
  an Admin presses Send again.

### Consequential test cases
- The key is never written to the database or a backup, never rendered after saving; a key file copied from another machine fails to decrypt (Windows) — Linux stand-in has owner-only permissions.
- Sending can't be switched on without the key and reply-to number.
- Off: a credit sale, payment or statement queues nothing; switching off abandons pending with the reason.
- The 200th message sends, the 201st pauses with the banner; next shop-time day resumes; raising the cap resumes.
- Two workers in threads over one queue: every message sent once, the daily count exact, never above the cap.
- A second process without the lock sends nothing.
- A message left `sending` for 10 minutes becomes abandoned "outcome unknown", is never resent automatically, and Send again queues a fresh send.
- A cashier sees the one-line status on a Khata but gets 403 on the Messages screen.
- Send test works with sending switched off, bypasses consent, counts toward the cap, is logged as a test, and reports each failure class in plain words.
