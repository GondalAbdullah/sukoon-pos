# 0035 — How Sukoon Starts on the Shop PC, and What That Decides About the WhatsApp Key

Status: **Accepted** 2026-09-17 — the client answered the 🛑 gate question in the Phase 7 grill
Date: 2026-09-17
Phase: 7
Grilled: `docs/proposals/phase-7-packaging.md` (D2, D2a, D3, D4)
Depends on: [ADR-0001](0001-technology-stack.md), [ADR-0023](0023-till-terminal-identity.md), [ADR-0033](0033-whatsapp-operational-safety.md)

## Context

The Development Specification's Phase 7 says Sukoon starts on login, and names
auto-start-on-login as one of three things "painful to change after client machines have real
data". The proposal (U2) challenged it: the shop has other tills that are only browsers
pointed at the shop PC, so if Sukoon starts at *login*, a 3 a.m. Windows Update restart leaves
every till dead until someone arrives and signs in.

A second fact arrived from measurement, not from the documents. `secret_store` protects the
WhatsApp access key with **user-scope DPAPI** (ADR-0033 §1). Measured on the Windows 11 VM,
2026-09-17, calling `CryptProtectData` directly:

| Logon the process runs under | User-scope DPAPI |
|---|---|
| Account signed in at the console | works |
| Key-authenticated SSH, nobody signed in | **fails, `0x5` access denied** |
| Machine scope (`CRYPTPROTECT_LOCAL_MACHINE`), either case | works |

User-scope DPAPI unlocks with the account's **password**. A logon that never carried one
cannot read the key. So *how Sukoon starts* decides *whether WhatsApp works after a reboot* —
and the failure mode is the quiet kind: selling, stock and Khata keep working while only
messages stop.

(This also corrects session 29's claim that the Windows-only paths "both work": the `msvcrt`
lock does, unconditionally; DPAPI is conditional. `context.md` §4 carries the correction.)

## Decision

1. **The server starts at boot**, as a background task, not on login. The tills work after any
   unattended restart, before anyone signs in. **Auto-start is on by default** — a shop PC
   exists to run the shop (the gate question, answered yes).
2. **It runs under a dedicated local Windows account** created by the installer, with a
   **randomly generated password stored by the task**. The owner never sees or types it.
   The account is set to *password never expires*; it is not a login the staff use.
3. **User-scope DPAPI is kept** (ADR-0033 §1 stands). The stored-credential logon is what makes
   it work — this is the reason to accept a stored password rather than a passwordless task.
4. **The key is bound to that account.** Reinstalling Windows, or recreating the account, means
   the saved key can no longer be decrypted and an Admin must paste it again. Recoverable, but
   the owner must be told: it goes in the install note and the handover checklist.
5. **The worker checks it can read the key when it starts**, not when the first message is due,
   and a failure raises the existing pause/banner path (ADR-0029 §7, ADR-0033 §4) saying the key
   can't be read. A quiet failure is the thing this ADR exists to prevent.
6. **The desktop window is separate from the server.** Closing the window closes only the
   window; the shop keeps selling (U3). Stopping the server is a deliberate, Admin-only action
   that warns how many tills have been in touch in the last minute.
7. **The production web server is Waitress** (D4) — pure Python, no compiler, Windows-supported.
   Flask's development server is never what ships; it stays for development only.

## Alternatives Considered

- **Start on login** (the specification's own wording, offered to the client). Simplest, and
  DPAPI would work because a console logon carries the password. Lost: the tills are dead
  between an unattended reboot and the owner's arrival, and the owner is not always first in.
- **Background task with no stored credentials** (a virtual/service account, or "S4U"). Avoids
  storing a password — but the measurement above says user-scope DPAPI then fails, so WhatsApp
  would break after every reboot. Rejected on evidence, not on taste.
- **Machine-scope DPAPI** (offered). Survives any logon type and any password change; would let
  us drop the stored password. Lost: any account on that PC could then decrypt the key, which
  is a real reduction from what ADR-0033 chose. **Trigger to revisit:** if the stored-credential
  task proves unreliable on the shop's Windows, or a password change is found to break the key
  in practice, machine scope is the fallback — and that trade is then made explicitly.
- **Ask for the key at startup.** Rejected on sight: the shop PC must come back from a power cut
  with nobody present.
- **A true Windows service** (D2-C). The most "proper" server, but more moving parts, and the
  service-account question lands in the same place as above with no extra gain.

## Consequences

- **Easier:** the shop survives unattended reboots; WhatsApp keeps working across them; closing
  a window can't take the shop down.
- **Harder:** the installer must create an account, generate and store a password, grant that
  one account write access to the data folder (ADR-0036), and the uninstaller must clean it up.
- **A new failure to document:** reinstalling Windows loses the saved WhatsApp key.
- **Windows-specific and untested until built:** every claim about how a scheduled task's logon
  behaves is **(verify)** until exercised on the VM — including whether changing that account's
  password invalidates the saved key.

### Consequential test cases
- The VM reboots with nobody signed in; a second machine's browser reaches the till screen.
- With the task running under the dedicated account, saving and reading back the WhatsApp key succeeds.
- A worker whose key cannot be decrypted pauses and shows the banner, and does not silently skip messages.
- Closing the desktop window leaves the server up and a second till still selling.
- "Stop Sukoon" warns when tills have been active in the last minute, and needs an Admin.
- After changing the dedicated account's password, the saved key is still readable — or, if not, the install note says so and the ADR is revisited.
