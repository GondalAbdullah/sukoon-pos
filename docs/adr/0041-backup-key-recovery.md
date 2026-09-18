# 0041 — Getting the Backup Key Back After a Reinstall

Status: **Accepted** 2026-09-18 — found on the VM the day before go-live
Date: 2026-09-18
Phase: 7
Amends: [ADR-0037](0037-offsite-backup-and-restore.md) §5
Depends on: [ADR-0033](0033-whatsapp-operational-safety.md) §1, [ADR-0035](0035-how-sukoon-starts-on-windows.md), [ADR-0036](0036-where-the-shops-data-lives.md)

## Context

ADR-0037 §5 said the offsite backups are locked with a key generated on the shop PC and printed on
a recovery sheet kept away from the shop. It did not say **how the key gets back into Sukoon**.

The uninstall test exposed the gap. Uninstalling removes the dedicated Windows account (ADR-0035
§2), and every secret is encrypted for that account (ADR-0033 §1) — so after an uninstall, a
Windows reinstall, or a move to a new PC:

- the data folder survives (ADR-0036 §3), but `backup-encryption.key` and the storage secret inside
  it **cannot be unlocked**;
- Sukoon answered with "Something went wrong" — the underlying error escaped as a 500;
- and **nothing in Sukoon accepted the printed sheet back**. The sheet existed and was useless
  except to a developer decrypting a backup by hand.

That is precisely the day the sheet is for.

## Decision

1. **An unreadable secret is explained, never a crash.** Both the backup key and the storage secret
   report, in the shop's words, that they were locked for a Windows account that no longer exists.
2. **Sukoon never silently makes a replacement key.** A new key would leave every backup already
   offsite locked with the old one, with nothing said and the owner's printed sheet no longer
   matching their backups. `encryption_key(create=True)` refuses when a key exists but cannot be read.
3. **The Settings screen takes the key from the recovery sheet**, typed exactly as printed — spaces
   and line breaks ignored, length and alphabet checked, with a message naming the likely typo.
4. **"Start a new key" exists, deliberately**: behind the Admin's own password (step-up), with a
   plain warning that every backup made before today can never be opened again. For the shop that
   has genuinely lost the sheet.
5. **The install checklist and the owner's guide say what the sheet is for**, and that it must not
   live on the shop PC or in WhatsApp.

## Alternatives Considered

- **Generate a new key automatically when the old one can't be read.** Sukoon would look healthy and
  keep backing up — while every earlier backup silently became unopenable. Rejected outright.
- **Keep the key in the database instead of DPAPI.** It would survive a reinstall with the data
  folder — and would also sit in every backup, so anyone with a backup would have the key that
  unlocks it. Rejected: that is the whole point of encrypting before upload (ADR-0037 §4).
- **Escrow the key with the developer.** Reliable recovery, and it makes the developer able to read
  the shop's books forever, including after handover. Rejected.
- **A passphrase the owner chooses** instead of a generated key: memorable, therefore weak, and a
  forgotten one destroys the backups with no artefact to hunt for (already rejected in ADR-0037).

## Consequences

- **Easier:** a shop that loses its PC can rebuild and reach its books with one printed page.
- **Harder:** that page has to exist. The recovery sheet moves from "good practice" to a required
  install step.
- **Unchanged by design:** without the sheet and without the PC, the offsite backups are
  unrecoverable — by anyone, including whoever built Sukoon.

### Consequential test cases
- A key that this PC cannot unlock: every offsite action explains itself; none returns a 500.
- Upload a backup, delete the key file, type the printed key back, and the same backup comes down readable with the shop's sales in it.
- A mistyped key is refused by alphabet or by length, and says which.
- "Start a new key" needs the Admin's own password, and afterwards the older backup fails to open — loudly.
- The storage secret being unreadable is reported separately: it can simply be pasted again from the storage account.
