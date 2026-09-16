# Phase 7 — Windows Packaging & Offline Installable App: Proposal for the grill session

Status: **PROPOSAL — nothing here is decided.** Written 2026-09-15 (session 28) as the
artefact for the `grill-with-docs` session the Development Specification requires before
Phase 7 code (step 1: "finalize the installer tool, auto-start method, database file location,
and update strategy"). Each open decision carries a **recommendation with reasoning**
(operating rule 10); the grill attacks them, and only what survives becomes an Accepted ADR.

Facts marked **(verify)** are believed, not confirmed against a current source.

The spec's 🛑 gate before closing Phase 7 names what is "painful to change after client
machines have real data": **the database file location, the backup file location, and whether
auto-start-on-login is on by default.** Those get the hardest questions.

---

## 1. What Phase 7 must deliver (Development Specification)

- pywebview desktop window over the Flask app; PyInstaller **onedir** bundle; Inno Setup
  installer (Start Menu, optional auto-start on login, database under a stable per-machine
  location, uninstall preserving data by default); a WebView2 runtime check with a clear
  fallback; the LAN addressing approach for cashier terminals.
- Required tests: fresh install on a clean Windows VM with no developer tools; uninstall
  preserves the database; upgrade-install keeps data; auto-start after reboot; full offline
  smoke test of every non-WhatsApp module with networking disabled.
- Edge-case matrix (also Phase 7): auto-start after restart; a locked/unexpectedly closed
  database recovers (WAL checkpoint); **a tested backup restore procedure**; the server's LAN
  address doesn't silently change.

## 2. Already settled — don't reopen without cause

| Source | What it fixes |
|---|---|
| ADR-0001 | Python + Flask + SQLite; **pywebview** (not Electron — accepts the WebView2 dependency); **PyInstaller onedir** (not onefile); **Inno Setup**; one host PC, other tills are browsers on the LAN; offline except WhatsApp. |
| ADR-0023 | Tills identify themselves by a browser cookie; nothing to install on them. |
| ADR-0024 | Shop time is a fixed setting; PC clock accuracy is the OS's job (Windows "Set time automatically"). |
| ADR-0033 §1, §7 | The WhatsApp key is DPAPI-encrypted, **bound to a Windows account this grill must name**; background jobs start only from an explicit launcher and one process holds the worker lock. |
| Code today | WAL + foreign keys + busy timeout on every connection (`app.py`); jobs start from `python -m sukoon.run`; CI runs lint and tests on Ubuntu. |

## 3. Things nothing in the project has raised yet

These are the unasked questions. They're listed first because each can sink the phase.

**U1 — Nothing here can build or test the Windows program.** PyInstaller does not
cross-compile: a Windows `.exe` must be built on Windows. The spec's required tests need a
clean Windows VM. This Linux machine has neither. *Who builds, and where are the clean-VM tests
run?* (D1)

**U2 — "Auto-start on login" means the tills are dead until someone logs in to the server PC.**
A Windows Update restart at 3 am leaves the other tills showing "can't connect" until the
owner arrives and logs in. It also decides DPAPI: a key protected for the owner's Windows
account can only be read by a process running as that account. (D2)

**U3 — Closing the window must not stop the shop.** If the pywebview window *is* the server
process, the owner closing it — or Windows asking to close apps — takes every till down
mid-sale. (D3)

**U4 — The Flask development server can't be what ships.** `app.run()` is Flask's development
server (its own docs say not for production). A production WSGI server that runs on Windows is
needed — a new dependency ADR-0001 didn't name. (D4)

**U5 — An installed copy has no way to create its first account.** Staff accounts come from
`flask seed` with passwords in environment variables; the shop owner has no terminal, and the
sample catalogue and dev users must never ship. `SECRET_KEY` also comes from the environment
today. (D5)

**U6 — A USB receipt printer may not work on Windows as-is.** `python-escpos`' USB mode on
Windows generally needs libusb and a WinUSB driver in place of the vendor's (e.g. via Zadig)
**(verify)** — which can break the vendor's own tools. A network (Ethernet) printer avoids it.
(D9)

**U7 — A backup on the shop PC dies with the shop PC, and nothing has asked whether the
shop's data may leave the shop.** D7 as first written keeps every copy on the same machine, so
theft, fire, a dead disk or ransomware loses everything; the client raised this in session 29
and asked for **Neon**. Copying customer names, numbers and debts to a third-party service is
also the first time anything but a consented WhatsApp message would leave the building. (D7a, D7b)

## 4. Decisions for the grill

### D1 — Where the program is built and tested (U1)

| Option | For | Against |
|---|---|---|
| **A. GitHub Actions `windows-latest` builds the installer on every tagged release, and runs scripted silent install → smoke test → upgrade → uninstall** *(recommended)* | Reproducible; runs on a clean Windows each time; free for a public repository **(verify)**; the build machine is never "the developer's laptop with things installed". | A CI runner isn't a real shop PC: no printer, no second till, and it can't prove the pywebview window looks right. |
| B. The developer builds on a Windows PC or VM by hand | Real desktop, real window. | Not reproducible; "works on my machine" is exactly what the clean-VM requirement exists to prevent. |
| C. Both: CI for the build and scripted tests, plus a manual checklist on a real Windows PC for the window, printer and LAN till | Covers both gaps. | Needs a Windows machine for the manual part. |

**Recommend C.** Question only the developer can answer: **is there a Windows PC or VM
available for the manual checklist?**

### D2 — How Sukoon starts (U2) — 🛑 gate item

| Option | For | Against |
|---|---|---|
| A. Start on login (as the spec says) | Simple; the owner sees the window; DPAPI under the owner's account just works. | Tills are down until someone logs in (U2). |
| **B. The server starts at boot as a background task; the window opens on login and connects to it** *(recommended)* | Tills work after any restart, before anyone logs in; closing the window never stops the shop (U3). | Two parts to install. The background task needs an account: running it as the owner's account "whether logged on or not" means Windows stores that account's password for the task **(verify)**; a dedicated local account is cleaner but DPAPI must then be bound to it. |
| C. A true Windows service | The most "proper" server. | More moving parts (a service wrapper), and a service account again changes DPAPI; no desktop window without a separate launcher anyway. |

**Recommend B**, with the background task under a dedicated local Windows account created by
the installer, and DPAPI bound to it (answers ADR-0033's open question). **Gate question:
should it start automatically by default?** Recommend **yes** — a shop PC exists to run the
shop.

### D2a — Measured: how Sukoon starts decides whether the WhatsApp key can be read

**This is no longer a guess.** Measured on the Windows 11 VM, 2026-09-17 (session 30), by
calling `CryptProtectData` directly:

| Logon the process runs under | User-scope DPAPI (what `secret_store` uses today) |
|---|---|
| Account signed in at the console | **works** |
| Key-authenticated SSH, nobody signed in | **fails, `0x5` access denied** |
| Machine scope (`CRYPTPROTECT_LOCAL_MACHINE`), either case | works |

User-scope DPAPI unlocks with the account's **password**. A logon that never carried one — an
SSH key session, and **(verify)** a scheduled task or service configured without stored
credentials (S4U, a virtual or group-managed account) — cannot decrypt it.

**Consequence for D2-B and D2-C:** running the server as a background task under a dedicated
account is still right for keeping the tills alive after an unattended reboot, but **that
account must log on with a stored password**, or Sukoon cannot read the WhatsApp key after a
restart. The failure is quiet in the worst way: sales, stock and Khata all keep working, and
only messages stop, with an error on a screen an Admin may not open for days.

**Options, for the grill:**

1. **Keep user-scope DPAPI and require a stored-credential logon** for the background task
   *(recommended)* — keeps the key bound to one account on one machine; the cost is that the
   installer (or the developer) sets that account's password on the task, and a Windows
   password change on that account **(verify)** may require re-entering the key.
2. **Machine scope**, so any process on the PC can decrypt it. Survives any logon type and any
   password change. Weaker: on a shop PC with one account and physical security, the practical
   difference is small, but it is a real reduction and ADR-0033 §1 chose user scope deliberately.
3. **Ask for the key at startup.** Rejected on sight: the shop PC must come back from a power
   cut with nobody present.

Whichever wins, two things follow: Sukoon should **check it can read the key when the worker
starts, not when a message is due**, and the Messages screen (and ideally the paused banner)
should say plainly that the key can't be read, rather than letting messages pile up.

### D3 — What closing the window does (U3)

**Recommend:** closing the window only closes the window; the server keeps running (under D2-B
it's a different process anyway). A **"Stop Sukoon"** action exists only for an Admin, with a
warning naming how many tills are connected in the last minute. Under D2-A it would have to
minimise to the tray instead.

### D4 — The production web server (U4)

**Recommend Waitress** — pure Python, no compiler, runs on Windows, widely used for Flask on
Windows **(verify current version)**. Bind to the LAN so tills can reach it (D8). The Flask
dev server stays for development only.

### D5 — First run on a new PC (U5)

**Recommend:** on first start with no users, Sukoon shows a **one-time setup screen** — shop
name, the owner's name and password (becomes the first Admin), and nothing else; it
disappears forever once an Admin exists. `SECRET_KEY` is generated on first start and stored
in the data folder (never shipped, never in the database). The installer **never** runs
`seed --sample`; permissions are seeded automatically on start.

### D6 — Where the data lives — 🛑 gate item

| Option | For | Against |
|---|---|---|
| **A. `C:\ProgramData\Sukoon\` — database, WhatsApp key, logs, backups subfolder** *(recommended)* | Per-machine, as the spec says; survives uninstall; not inside Program Files (which standard users can't write to); the same for every Windows account. | ProgramData folders created by an installer are read-only for ordinary users by default **(verify)** — the installer must grant the Sukoon account write access, and only that account. |
| B. The owner's `%LOCALAPPDATA%` | Writable with no permission work. | Per-user, not per-machine: a different Windows login sees an empty shop; fails the spec. |
| C. Next to the program in Program Files | Easy to find. | Not writable without admin rights; upgrades risk overwriting data. |

### D7 — Backups — 🛑 gate item

- **How:** SQLite's online backup API (safe while the shop is selling), **not** a file copy
  of a database in WAL mode — copying the `.db` alone can miss recent writes **(verify —
  standard SQLite guidance)**.
- **When:** recommend **every day at closing time (configurable, default 23:00) and before every
  upgrade's migration**, keeping the last **14 daily** plus the **pre-upgrade** ones.
- **Where:** recommend `C:\ProgramData\Sukoon\backups\` **plus** an optional second folder (a USB
  drive or another disk) an Admin can set — a backup on the same disk doesn't survive a dead
  disk. **Gate question:** is a same-PC backup acceptable as the default, with the second copy
  optional?
- **Restore:** an Admin-only, step-up "Restore from backup" that stops the server, keeps a copy
  of the current database first, restores, and restarts. **Tested as a drill** (edge-case matrix;
  Phase 8 repeats it).

### D7a — Offsite backup: the client's Neon request (raised session 29) — 🛑 gate item

D7 keeps every backup on the shop PC, with an optional second folder. The client asked for
the shop's data to be copied to **Neon** (a hosted Postgres service) so that a dead, stolen,
burnt or ransomwared PC doesn't take the shop's books with it. **The requirement is right and
D7 does not meet it.** What follows is about the *destination and mechanism*, not the need.

**What any offsite backup here must satisfy** (from existing ADRs, not new opinions):

- It **never blocks or slows a sale** (ADR-0003: a secondary action never breaks a primary one).
- It **survives days without internet** and catches up — the shop's connection is unreliable,
  which is why the whole app is offline-first (ADR-0001).
- Its **restore is drilled, not assumed** (D7, and the spec's edge-case matrix). An untested
  backup is a belief, not a backup.
- It is **encrypted before it leaves the PC**, and its key/credentials live in the DPAPI store,
  never in the database or the backup itself (ADR-0033 §1).
- Its freshness is **visible** — a "last backup" line and an alert when it goes stale — because
  a silently broken backup is worse than none.

| Option | For | Against |
|---|---|---|
| **A. Encrypted database-file backup to object storage** (SQLite online-backup → compress → encrypt → upload to an S3-compatible bucket, e.g. Cloudflare R2 or Backblaze B2) *(recommended)* | One format, one schema, no second copy of the data model; restore is "download, decrypt, put the file back" and can be drilled in minutes; tiny (a shop-year of data is small); works with the D7 machinery already proposed; a day's worth of history is a rotation setting, not new code. | Recovery point is the last upload (recommend **hourly during trading hours plus one at close**); needs a storage account and a key the client must keep safe **outside** the shop. |
| B. Continuous replication of SQLite's write-ahead log (Litestream-style) to the same object storage | Near-zero data loss; point-in-time restore ("the state at 4:05 pm"). | Another moving part running beside the app; **Windows support must be confirmed (verify)**; still object storage — it does not answer "Neon". |
| C. **Mirror the rows into Neon Postgres** — what was asked for | A remote, queryable copy; Neon has a free tier **(verify)**; the data is readable without restoring anything. | Every table then exists in **two different databases with two different type systems**, so **every future migration must be written and tested twice**, forever. Needs a sync engine nobody has specified: change tracking, ordering, foreign keys, deletes, resumption after days offline. The restore path is a Postgres→SQLite converter that must be **written and drilled** — needed exactly once, in the worst hour of the shop's life. Its characteristic failure is **silent drift**: the mirror looks healthy and isn't. Buys nothing for recovery that A doesn't, unless remote querying is itself a requirement — and nobody has asked for one. |
| D. Move the whole app to Neon (Postgres as the live database) | No sync at all; one database. | **Rejected by ADR-0001**: the shop must keep selling with no internet. A hosted database makes every sale depend on a connection this shop does not reliably have. |

**Recommend A**, with **B as a later upgrade** if the client wants a tighter recovery point, and
**C only if remote access to the data becomes a real requirement of its own** — in which case it
is a *reporting mirror*, and A remains the restore path. **Gate questions for the client:**
(1) is an hourly offsite copy enough, or is "no more than a few minutes lost" required?
(2) who holds the encryption key and the storage login, given the developer hands the shop over?

### D7b — The shop's data leaving the shop (U7)

Nothing in the project has yet asked whether the shop's records *may* be copied to a
third-party service. Today only WhatsApp messages leave the PC, only for customers who
consented (ADR-0028). An offsite backup is different in kind: **every customer's name, phone
number, purchase history and debt**, continuously, to a company in another country
**(verify where the chosen provider stores data)**. This needs the client's informed agreement
recorded — not the developer's assumption — plus encryption before upload so the provider
holds only ciphertext. **Question for the client, in plain terms: may the shop's books be kept,
encrypted, on a server outside Pakistan, so they survive the PC?**

### D8 — How tills find the server (step 6)

| Option | For | Against |
|---|---|---|
| **A. Fixed address via the router's DHCP reservation, tills bookmark `http://192.168.x.x:5000`** *(recommended)* | Works with any router, no Windows changes; the address never drifts. | Needs someone to set the reservation on the router once. |
| B. The PC's name, `http://SHOP-PC:5000` | Nothing to configure. | Name resolution on small networks is unreliable, especially from phones **(verify)**. |
| C. Static IP set in Windows | No router access needed. | Collides with the router handing the same address to another device. |

Plus: the installer adds a **Windows Firewall inbound rule for the Sukoon port on private
networks only**; Sukoon shows its own LAN address on the Settings screen so a till can be
pointed at it.

### D9 — Receipt printers on Windows (U6)

**Recommend:** support **network printers** as the recommended setup and **Windows-installed
printers** (printing through the Windows spooler) instead of raw USB; keep raw USB only for
printers that work with it. **Question for the client: what printer does the shop have — model,
and USB or Ethernet?**

### D10 — WebView2 (step 5)

**Recommend:** bundle Microsoft's **Evergreen bootstrapper** in the installer and run it only when
WebView2 is missing **(verify: Windows 11 ships it; most updated Windows 10 PCs have it)**. If it
can't be installed (no internet on a truly offline PC), the installer says so plainly and Sukoon
still works in any browser at `http://localhost:5000`. Bundling the full offline runtime
(large) is the fallback option if the shop PC is permanently offline.

### D11 — Updates

**Recommend:** no auto-update (the PC may be offline, and an unattended upgrade mid-sale is
worse than a manual one). An update is **the developer delivering a new installer**, run over the
existing install. On first start after an upgrade, Sukoon **backs up, then runs migrations**; if
a migration fails it restores the backup and shows a clear error instead of a half-migrated
database. Tested by the spec's upgrade-install test with real data.

### D12 — Trust warnings

An unsigned installer triggers Windows SmartScreen ("Windows protected your PC") and PyInstaller
bundles are sometimes flagged by antivirus **(verify)**. Code-signing certificates cost money
yearly. **Recommend:** ship unsigned for the first client with a one-page install note showing the
"More info → Run anyway" step; revisit signing if more shops install it. **A cost decision for
the client.**

## 5. Proposed out of scope for Phase 7

Auto-update; installing anything on the other tills; cloud backup; a macOS/Linux build;
multi-shop. (Phase 8 is full integration testing and UAT.)

## 6. After the grill, the build (not before)

1. ADRs. 2. Waitress launcher, background task and window launcher (D2–D4). 3. First-run setup,
generated `SECRET_KEY`, data folder (D5–D6). 4. Backup, restore, pre-upgrade backup and migration
safety (D7, D11). 5. PyInstaller spec and Inno Setup script (firewall rule, account, permissions,
WebView2, uninstall keeping data). 6. Windows CI: build, silent install, smoke test, upgrade,
uninstall (D1). 7. The Windows-only paths finally exercised: DPAPI and the `msvcrt` worker lock
(context.md §4). 8. The manual Windows checklist: window, printer, a second till, offline smoke
test with networking disabled.
