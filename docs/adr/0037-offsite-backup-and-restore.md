# 0037 — Offsite Backup, Encryption, and the Restore Drill

Status: **Accepted** 2026-09-17 — the client answered the 🛑 gate questions in the Phase 7 grill
Date: 2026-09-17
Phase: 7
Grilled: `docs/proposals/phase-7-packaging.md` (D7, D7a, D7b)
Resolves: **O-24** (the client's Neon request)
Depends on: [ADR-0001](0001-technology-stack.md), [ADR-0003](0003-module-boundaries.md), [ADR-0033](0033-whatsapp-operational-safety.md), [ADR-0035](0035-how-sukoon-starts-on-windows.md), [ADR-0036](0036-where-the-shops-data-lives.md)

## Context

The proposal's D7 kept every backup on the shop PC. The client raised the gap on 2026-09-16:
theft, fire, a dead disk or ransomware takes the PC *and* its backups. They asked for the data
to be mirrored to **Neon** (hosted Postgres), and in the grill asked the sharper question —
*is there a cloud database based on SQLite?*

There is: **Turso/libSQL** (hosted, SQLite-compatible), **Cloudflare D1**, **SQLite Cloud**, and
**Litestream**, which is not a database service but continuous replication of a SQLite file to
object storage. Litestream was the best fit for the actual requirement and was the client's
first choice in the grill — **until it was checked**: the current release (v0.5.17,
2026-08-31) states *"Windows binaries are provided for convenience but Windows is NOT an
officially supported platform."* Disaster recovery is the one component that must work on the
day everything else has failed, so it was withdrawn rather than adopted on an unsupported
build. The check happened because the option was recorded as conditional, not waved through.

**Measured, so the cadence is not guesswork** (2026-09-17, seeded on this machine): a full year
at ~120 sales/day — 43,800 sales, 175,200 line items — is **13.1 MB on disk, 3.1 MB gzipped**.

## Decision

1. **The restore path is an encrypted copy of the SQLite database in object storage.** Not a
   row mirror into another database engine.
   - Made with **SQLite's online backup API**, which is safe while the shop is selling — never a
     file copy of a database in WAL mode.
   - Compressed, then **encrypted on the shop PC** before upload. The provider stores ciphertext.
   - Destination: an **S3-compatible bucket** (Cloudflare R2 / Backblaze B2 or similar); the
     chosen provider and its region are recorded when the account is created **(verify pricing
     and region at that point)**.
2. **Cadence: every 15 minutes during trading hours**, plus one at closing and one **before any
   upgrade's migration**. Worst case loses ~15 minutes of trading — sales the cashier can
   re-enter from the printed receipts. **Bandwidth, measured:** ~3 MB per upload at a year of
   data, ~56 uploads/day ⇒ **~170 MB/day, ~5 GB/month at year-end size**, less before that.
   **(Client fact needed: if the shop is on metered mobile data, drop to hourly — recorded as
   an open item, not assumed.)**
3. **Retention:** the last 24 hours at 15-minute granularity, then **14 daily**, plus every
   **pre-upgrade** backup. Old objects are deleted by Sukoon, not left to grow forever.
4. **Yes, the data may leave Pakistan — encrypted** (the client's answer to D7b). The shop holds
   the only key. The owner is told plainly, in the install note and at setup, what is stored
   and where. Customer names, phone numbers, balances and sales are what leaves.
5. **The key that decrypts backups is generated at setup and shown once as a printed recovery
   sheet** — the key, what it unlocks, and a warning that losing it makes every backup
   unreadable. The owner keeps a copy off the premises; the developer keeps one during the
   engagement and hands it over at the end. It is **never** stored only on the shop PC: a fire
   that takes the PC would otherwise take the key with it.
6. **A weekly self-check proves the backup is real:** Sukoon downloads its own most recent
   backup, decrypts it, opens it, and checks the newest sale is present — then records the
   result where an Admin sees it, with a visible "last verified" line and a warning when it
   goes stale. A backup that cannot be decrypted must fail on a quiet Tuesday, not in a disaster.
7. **One full rehearsal before handover:** wipe the VM, install fresh, restore from the cloud
   copy, confirm the books match. Documented as a procedure the developer can repeat.
8. **Backing up never blocks a sale** (ADR-0003). It runs in the background job process; a
   failed upload retries and, after repeated failures, raises a visible warning — the same
   discipline as WhatsApp's outbox, and for the same reason.

## Alternatives Considered

- **Row mirror into Neon Postgres** — the client's original request, and offered again in the
  grill. Lost: the schema would exist in two engines, so **every future migration is written and
  tested twice**; it needs a sync engine nobody has specified (change tracking, ordering,
  foreign keys, deletes, resumption after days offline); the restore path becomes a
  Postgres→SQLite converter exercised once, in a disaster; and its characteristic failure is
  **silent drift** — a mirror that looks healthy and isn't.
- **Litestream** (continuous replication; the client's first choice). Lost **only** to its own
  release notes: Windows is not an officially supported platform. **Trigger to revisit:**
  Litestream declares Windows supported, or an equivalent tool with Windows support appears.
- **Hosted SQLite (Turso/libSQL) as a live copy** (offered). Genuinely SQLite-compatible, so no
  duplicate schema — but it changes the database driver the whole app uses (an ADR-0001-level
  change needing its own grill), and its offline-write story needs verification before a shop
  that loses internet daily could depend on it. **Trigger to revisit:** a future need for remote
  querying, or multi-branch.
- **Neon as the live database** (D7a-D). Rejected against ADR-0001: the shop must keep selling
  with no internet.
- **Local plus a USB drive only** (offered). No third party, no consent question — and it
  survives fire or theft only if a human remembers to take the drive home. Kept as the fallback
  if the client later refuses offsite storage.
- **Provider-managed encryption** (offered). Simplest, and it lets the provider read the shop's
  books — which defeats the point of the client's own answer to D7b.
- **An owner-chosen passphrase** instead of a generated key (offered). Nothing to store; but
  shop owners choose weak, memorable phrases, and a forgotten one destroys the backups with no
  artefact to hunt for.
- **One drill before handover, with no ongoing check** (offered). Proves it worked once, on one
  day; a backup that quietly stops three months later is discovered in the disaster.

## Consequences

- **Easier:** a dead shop PC costs ~15 minutes of trading, not the year. One schema, one file
  format, a restore that is download-decrypt-replace and is rehearsed weekly by the software
  itself.
- **Harder:** a storage account and its credentials must exist, be paid for, and be handed over;
  the recovery sheet is a physical artefact that can be lost; ~5 GB/month of upload at year-end.
- **A real obligation to the shop's customers:** their names, numbers and debts now leave the
  building. Encryption is what makes that acceptable, and the owner is told in plain words.
- **Forecloses nothing:** a Neon or Turso mirror can still be added later as a *reporting*
  convenience; this decision only fixes what the shop's survival depends on.

### Consequential test cases
- A backup taken while sales are being written restores to a database containing those sales (online backup API, not a file copy).
- The uploaded object is unreadable without the key; with the key it opens and the newest sale is present.
- The weekly self-check fails loudly when the object is corrupted, when the key is wrong, and when the newest sale is missing.
- Retention deletes what it should and never deletes a pre-upgrade backup.
- A 15-minute run during a network outage retries, does not block any sale, and warns after repeated failures.
- Full drill: fresh Windows, fresh install, restore from cloud, books match the source machine row for row.
- Pre-upgrade backup exists and is restorable when a migration fails (ADR-0038's rollback path).
