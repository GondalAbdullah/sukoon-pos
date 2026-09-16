# 0036 — Where the Shop's Data Lives on the Windows PC

Status: **Accepted** 2026-09-17 — the client answered the 🛑 gate question in the Phase 7 grill
Date: 2026-09-17
Phase: 7
Grilled: `docs/proposals/phase-7-packaging.md` (D6)
Depends on: [ADR-0001](0001-technology-stack.md), [ADR-0035](0035-how-sukoon-starts-on-windows.md)

## Context

The Development Specification names the database file location as one of three things painful
to change once client machines hold real data. Two constraints narrow it:

- Sukoon's server runs under a **dedicated local account** (ADR-0035 §2), so the data must sit
  somewhere that account can write and that is not tied to any person's Windows profile.
- Uninstalling must **not** take the shop's books with it.

## Decision

1. **`C:\ProgramData\Sukoon\`**, fixed — not configurable at install. One path on every machine,
   so a support question has one answer.
   - `sukoon.db` (plus its WAL files), `logs\`, `backups\`, `whatsapp.key`, and the generated
     `SECRET_KEY` file. Nothing of the shop's lives in Program Files.
2. **The installer grants write access to the Sukoon account only**, and removes inherited
   permissions, so other Windows users on the PC cannot read or alter the books directly.
   *(ProgramData folders are read-only for ordinary users by default — **(verify)** the exact
   ACL the installer must set.)*
3. **Uninstall keeps the data** by default, and says so on screen. Removing it is a separate,
   explicit choice.
4. **An upgrade never writes to this folder except through a migration**, and the migration is
   preceded by a backup (ADR-0037 §4).
5. The Settings screen shows the folder path, so support doesn't depend on memory.

## Alternatives Considered

- **ProgramData by default, changeable at install** (offered). Useful for a second disk. Lost:
  a setting that can be wrong once and is discovered months later, and every support
  conversation starts with "where did you put it?". **Trigger to revisit:** a shop PC whose
  Windows drive is too small or genuinely unreliable.
- **A folder the owner picks, e.g. on the desktop** (offered). Recognisable — and per-user, so a
  second Windows login sees an empty shop, and staff can move or "tidy" what they can see.
  This is how data gets lost. Rejected.
- **`%LOCALAPPDATA%`** (proposal D6-B). Writable with no permission work, but per-user: fails
  the specification's per-machine requirement outright, and fails harder now that the server
  runs as its own account.
- **Next to the program in Program Files** (D6-C). Not writable without admin rights; upgrades
  risk overwriting data. Rejected.

## Consequences

- **Easier:** one path everywhere; uninstall is safe; the service account's permissions are a
  single, auditable grant.
- **Harder:** the installer must set ACLs correctly, and get them right on upgrade too — a
  wrong ACL means Sukoon cannot write, which must fail loudly at startup, not at the first sale.
- **The folder is hidden from casual browsing**, which is deliberate: the owner reaches their
  data through Sukoon's own backup and export features, not Explorer.

### Consequential test cases
- Fresh install creates the folder; the Sukoon account can write; a standard user account cannot read the database.
- Uninstall leaves the folder and its contents; a re-install finds the existing database and does not overwrite it.
- Upgrade-install with real data keeps every row (the spec's upgrade test).
- Sukoon started with an unwritable data folder refuses to start with a clear message naming the folder, rather than failing at the first sale.
- The Settings screen shows the real path.
