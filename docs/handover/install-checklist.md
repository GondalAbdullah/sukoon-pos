# Installing Sukoon at the shop — checklist

For the person installing Sukoon on the shop PC on go-live day. Work top to bottom; tick as you go.
Every step here exists because something failed, or was found to be a trap, while testing the
installer (context.md, sessions 32–33).

## Before you go

- [ ] `Sukoon-Setup-1.0.0.exe` on a USB stick, plus this checklist printed.
- [ ] The shop PC's Windows edition and version (Settings → System → About). Windows 10 or 11, 64-bit.
- [ ] The router's admin password (usually on a sticker on the router), for the reserved address.
- [ ] The receipt printer's make and model (O-25).

## 1. The shop PC

- [ ] **Signed in as an administrator** account. The installer needs it.
- [ ] **Date, time and time zone correct**, "Set time automatically" on. Receipts and the invoice year
      depend on it (ADR-0024).
- [ ] **The network is Private, not Public.** Settings → Network & internet → (the network) →
      *Private network*. On a Public network the firewall blocks the other tills. The installer
      warns if it finds Public, but fix it first.

## 2. Run the installer

- [ ] Double-click `Sukoon-Setup-1.0.0.exe`. Windows shows **"Windows protected your PC"** because the
      installer isn't signed (ADR-0038 §12): **More info → Run anyway**.
- [ ] Accept the defaults. Tick the desktop shortcut.
- [ ] If a **"Sukoon is installed, but needs attention"** box appears, do what it lists. The same list
      is in `C:\ProgramData\Sukoon\install.log`.
- [ ] If a **"setting up its server did not finish"** box appears, Sukoon will not run. Read the last
      lines of `C:\ProgramData\Sukoon\install.log` (they say what failed and on which line) before
      trying again.
- [ ] Antivirus: if it quarantines `sukoon-server.exe` or `Sukoon.exe`, restore them and add
      `C:\Program Files\Sukoon` as an exclusion. Then run the installer again.

## 3. First run — on the shop PC itself

- [ ] Open **Sukoon** from the desktop. The first screen is **Set up Sukoon**. It only works on the
      shop PC; other tills are told to finish setup here.
- [ ] Shop name exactly as it should print on receipts. The **owner** types their own name and a
      password of at least 8 characters. Don't choose the password for them.
- [ ] You land on the Sukoon home screen with Till, Stock, Khata, Insights, Messages and Refunds. If
      Khata or Insights are missing, stop: the owner is not a full Admin.

## 4. The other tills

- [ ] On the router: **reserve the shop PC's address** (ADR-0038 §10-A). Sukoon's address is on its
      Settings screen. No router or no router access? Use setup option B: a fixed address in Windows,
      **outside** the range the router hands out.
- [ ] On each other till: open Edge or Chrome at `http://<shop PC address>:5000` and bookmark it.
- [ ] On each till, name it once when the till screen asks ("Till 2", …).

## 5. Prove it works before you leave

- [ ] **Ring a real sale** on the shop PC and on every other till. Void it with a refund if needed.
- [ ] **Restart the shop PC and don't sign in.** Within about a minute, the other tills must
      reach Sukoon again. Tested on 2026-09-17: the server was answering 21 seconds after Windows
      started.
- [ ] **Receipt printer:** ring a sale. If "Printer unavailable" shows, PDF receipts still work;
      record the model for O-25.
- [ ] A backup exists: `C:\ProgramData\Sukoon\backups\` holds a `sukoon-….db` from the last 15
      minutes. You need administrator rights to open this folder.

## What is NOT switched on at go-live

- **WhatsApp messages** stay off until one real message has been sent and confirmed (O-23).
- **Offsite backup** doesn't exist yet (O-26). Backups are on this PC only, every 15 minutes, so a
  dead disk, a theft or a fire loses the books until offsite backup is set up. Tell the owner.

## If something goes wrong later

| What the shop sees | Where to look |
|---|---|
| Tills say "can't connect" | Is the shop PC on? Is its network Private? `install.log` and `logs\sukoon.log` in `C:\ProgramData\Sukoon\` |
| The Sukoon window says "server isn't running" | Restart the PC. If it persists, the last lines of `logs\sukoon.log` say why |
| "Sukoon did not start: upgrading the database … failed" | The backup taken just before was put back automatically; the shop's data is as it was. Keep the log and call the developer |
