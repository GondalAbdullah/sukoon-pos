# 0038 — Packaging, Installation, First Run, and How Updates Reach the Shop

Status: **Accepted** 2026-09-17 — decided in the Phase 7 grill; the commercial and practical questions answered by the client
Date: 2026-09-17
Phase: 7
Grilled: `docs/proposals/phase-7-packaging.md` (D1, D5, D8, D10, D11, D12)
Depends on: [ADR-0001](0001-technology-stack.md), [ADR-0023](0023-till-terminal-identity.md), [ADR-0035](0035-how-sukoon-starts-on-windows.md), [ADR-0036](0036-where-the-shops-data-lives.md), [ADR-0037](0037-offsite-backup-and-restore.md)

## Context

Everything so far has run from a developer's terminal. Phase 7 turns Sukoon into a program a
shop owner installs. The proposal raised what nothing in the project had: an installed copy has
**no way to create its first account** (staff come from `flask seed` with passwords in
environment variables, and `SECRET_KEY` comes from the environment); nothing here can build a
Windows `.exe`; and the specification's fresh-install test needs a Windows machine with no
developer tools, which our VM no longer is.

## Decision

### Building and testing
1. **The Windows VM is the build machine** for Phase 7 (`win11`, Windows 11 build 26200,
   Python 3.12.10, reached over key-only SSH). It answers U1. PyInstaller cannot
   cross-compile, so nothing about this can be done on the Linux laptop.
2. **The clean-machine test uses snapshot-and-revert** (the client's choice): Python and Git are
   uninstalled, that state is snapshotted as `clean-windows`, and every fresh-install test
   reverts to it. **Its weakness is recorded rather than glossed:** a machine that once held
   developer tools can mask a missing dependency, which is precisely what this test exists to
   catch. Two mitigations are required, not optional: the installed program must be proven to
   run with **Python removed and the PATH cleaned**, and a **genuinely untouched VM** is built
   before handover if disk space allows. **Trigger:** the fresh-install test passing on a
   reverted snapshot but failing, or being doubted, on a real shop PC.
3. **Automated Windows CI is not adopted now.** The repository is private, so runner minutes are
   a real cost **(verify the current free allowance)**, and the VM already provides a real
   desktop, which a runner cannot. **Trigger to revisit:** a second developer, or a second shop.

### The program
4. **PyInstaller onedir + Inno Setup + pywebview + Waitress**, as ADR-0001 and ADR-0035 fix.
   The installer creates the Start Menu entry, the dedicated account and its stored-password
   boot task (ADR-0035), the data folder and its ACLs (ADR-0036), and a **Windows Firewall
   inbound rule for Sukoon's port on private networks only**.
5. **WebView2**: bundle Microsoft's Evergreen bootstrapper and run it **only if WebView2 is
   missing** **(verify: Windows 11 ships it)**. If it cannot be installed — a PC with no
   internet at all — the installer says so plainly and Sukoon still works in any browser at its
   own address. The full offline runtime is the fallback if a shop PC is permanently offline.

### First run
6. **A one-time setup screen**, shown only while no user exists: shop name, and the owner's
   name and password, which becomes the first Admin. It disappears permanently once an Admin
   exists. This replaces `flask seed` for installed copies.
7. **`SECRET_KEY` is generated on first start** and stored in the data folder — never shipped in
   the installer, never in the database, never in a backup that could be read with it.
8. **The installer never runs `seed --sample`.** The sample catalogue and development users must
   not reach a shop. Permissions are seeded automatically on start; sample data never is.
9. **The setup screen also shows the backup recovery sheet once** (ADR-0037 §5) and tells the
   owner, in plain words, what leaves the shop and where it goes.

### On site
10. **Two supported network setups, not one assumption.** Sukoon **shows its own LAN address on
    the Settings screen** in both, so a till can be pointed at it without anyone hunting through
    Windows.
    - **A. Router-reserved address** *(the client's answer, and the default)*. The tills are
      wired into the shop's router; the router is told once to always hand the shop PC the same
      address. Nothing is changed in Windows, and it survives power cuts.
    - **B. No router — a fixed address set in Windows** *(a first-class fallback, not an
      afterthought)*. For a shop wired through a plain switch, a router whose settings nobody can
      reach (lost admin password, an ISP-locked box), or one that refuses reservations. The
      installer offers this as an explicit choice, sets the address on the shop PC, and the
      install note records the address used. **Chosen outside the range any router on the
      network hands out**, so it cannot later be given to a phone — the failure that makes
      option B dangerous when done carelessly.
    - **Both are supported paths with their own install-note section and their own test**;
      neither is "what you do when the real way fails". The shop is asked which it has during
      installation rather than assumed to have a router.

### Updates and trust
11. **No auto-update** (the client's answer). An update is an installer the developer runs over
    the existing install. On first start after an upgrade Sukoon **backs up, then migrates**; if
    a migration fails it **restores that backup** and shows a clear error rather than leaving a
    half-migrated database.
12. **The installer ships unsigned**, with a one-page install note showing Windows'
    "More info → Run anyway" step (the client's answer: the developer installs it for this
    shop, so the warning is seen once, by them). **Antivirus behaviour is tested on the VM
    before handover**, because a quarantined program at handover is an ugly surprise.
    **Trigger to revisit:** a second shop wanting to install Sukoon, which makes a
    code-signing certificate worth its annual cost.

## Alternatives Considered

- **GitHub Actions `windows-latest` for builds and scripted install tests** (proposal D1-A,
  recommended there). Reproducible and always clean — but costs runner minutes on a private
  repository and cannot prove the desktop window, the printer or a second till. Deferred, not
  rejected.
- **A second VM from the same ISO** (offered). The specification's requirement read strictly;
  lost to disk space (41 GB free) and the hour it costs. The mitigations above exist because
  this is the weaker choice.
- **Rebuild the dev VM after packaging** (offered). A true clean machine, but the install test
  then happens last, so what it reveals arrives at the worst moment.
- **Sukoon checks for updates and notifies** (offered). Lost: it needs a published location that
  must outlive the engagement — an obligation the developer cannot honour after handover.
- **Automatic updates** (offered). Rejected: an unattended upgrade mid-trading is worse than a
  delayed one, and a bad release would reach the shop with nobody watching.
- **Buying a code-signing certificate now** (offered). Removes the warning and names a
  publisher; lost to a recurring annual cost for a single shop, and a renewal that needs
  someone who still cares in 2028.
- **The PC's name instead of a reserved address** (proposal D8-B). Name resolution on consumer
  networks is unreliable, especially from phones and tablets.
- **Assuming every shop has a reachable router** (this ADR's first draft, corrected in the
  session by the developer). A shop may be wired through a plain switch, or have a router whose
  admin password nobody has. Leaving that case as a sentence of prose would have meant
  discovering it on installation day, on site, with the shop waiting. It is now setup option B
  with its own test.
- **Seeding the first Admin from the command line.** The shop owner has no terminal, and
  passwords in environment variables have no place on a client machine.

## Consequences

- **Easier:** a shop owner can install Sukoon and reach a working till without a developer
  typing commands; upgrades cannot silently corrupt a database; the tills have a stable address.
- **Harder:** the installer now does real system work — an account, a task with a stored
  password, ACLs, a firewall rule, a possible WebView2 install — and each is a way a fresh
  install can fail on a machine we have never seen.
- **Accepted risk:** the clean-machine test runs on a reverted snapshot, not a virgin Windows.
  Named above, with mitigations and a trigger.
- **Honest limits:** every Windows behaviour here is **(verify)** until exercised on the VM —
  the free CI allowance, WebView2's presence on the shop PC, and how antivirus treats a
  PyInstaller bundle.

### Consequential test cases
- Silent install on the reverted `clean-windows` snapshot, then a sale rung from a browser on the host — with Python uninstalled and the PATH cleaned.
- First start shows the setup screen; creating the first Admin makes it disappear permanently; a second start never shows it again.
- `SECRET_KEY` is generated once, lives in the data folder, and differs between two fresh installs.
- No sample product or development user exists after a fresh install.
- Upgrade-install over a database with real data: backup taken first, migration applied, every row intact.
- A deliberately failing migration restores the pre-upgrade backup and reports it.
- Uninstall keeps the data folder (ADR-0036); re-install finds it.
- The firewall rule exists for private networks only; a till on the LAN reaches the server, and the port is not open on a public profile.
- The Settings screen shows the machine's real LAN address, in both network setups.
- Setup option B: with no address-giving router present, the installer sets a fixed address, a second machine on the switch reaches the till screen, and the address survives a reboot of both machines.
- The fixed address chosen in option B lies outside the DHCP range when a router is present, and Sukoon warns if it detects a conflict.
- Windows SmartScreen and the installed antivirus are exercised on the VM and the behaviour documented in the install note.
