# 0039 — Receipt Printing on Windows, and the Printer a Background Account Cannot See

Status: **Accepted** 2026-09-17 — the client named the hardware in the Phase 7 grill; the model is still outstanding (O-25)
Date: 2026-09-17
Phase: 7
Grilled: `docs/proposals/phase-7-packaging.md` (D9, U6)
Depends on: [ADR-0003](0003-module-boundaries.md), [ADR-0035](0035-how-sukoon-starts-on-windows.md)

## Context

Receipts are printed with `python-escpos`, which speaks thermal printers' own language. The
proposal (U6) flagged that its **raw USB** mode on Windows generally needs libusb and a WinUSB
driver in place of the vendor's **(verify)** — a swap that can break the vendor's own utilities
and is unpleasant to support remotely.

The client's answer in the grill: **the shop has a USB thermal printer.**

That answer collided with ADR-0035, and the collision is the substance of this ADR. **Sukoon's
server runs as a dedicated background account.** Printers installed in Windows are ordinarily
installed *for the person who installed them*. A printer set up under the owner's login may be
invisible to the background account — which produces the worst kind of failure: receipts print
while the owner is signed in, and silently fall back to PDF when they are not. That is the same
shape as the DPAPI problem measured on 2026-09-17, found the same way: by asking what a
decision collides with.

## Decision

1. **Print through the Windows printing system** (the spooler), not raw USB. It avoids the
   driver swap, keeps the vendor's tools working, and is the documented path for a USB thermal
   printer. Raw USB stays available in configuration for a printer that needs it.
2. **The printer must be installed for the machine, not for one user**, and the installer's
   documentation says so explicitly. **(verify on the VM and then on the shop's hardware:
   whether the background account can enumerate and print to a machine-installed printer.)**
   Until verified, this is the largest untested assumption in Phase 7's printing path.
3. **A "Print a test receipt" action** exists for an Admin, and it prints **from the server
   process** — the same process that prints real receipts — so it proves the path that matters
   rather than the one the browser happens to have.
4. **Printing never blocks a sale** (ADR-0003, unchanged). A failure falls back to the PDF
   receipt and is logged. **New:** a printing failure is also **visible**, not only logged —
   an Admin-facing notice — because a shop that silently stops printing may not notice for days.
5. **Network printers stay the recommendation for any future shop**, and the configuration keeps
   supporting them: a printer on the LAN is not tied to one PC, needs no driver, and works
   identically from every till.

## Alternatives Considered

- **Raw USB via libusb/WinUSB** (proposal D9's status quo). Direct, and the ESC/POS path already
  written — but requires replacing the vendor's driver on the shop's PC, which can break the
  vendor's utilities and is hard to talk someone through over the phone.
- **A network printer** (offered, and recommended if buying). Lost only because the shop already
  has a USB printer; no reason to make them buy hardware.
- **PDF receipts only** (offered). Removes the hardware dependency entirely, and Sukoon already
  falls back this way — but a customer disputing a Khata entry then has no paper, and the shop
  hands out nothing at the counter.
- **Printing from the browser** instead of the server. Would sidestep the account question
  entirely, but puts a print dialog between the cashier and the next customer, and each till
  would need its own printer setup. Rejected against ADR-0003's separation and the till's speed.

## Consequences

- **Easier:** no driver surgery on the shop's PC; the vendor's own tools keep working.
- **Harder:** the installer (or the install note) must ensure the printer is installed
  machine-wide, and this cannot be proven here — it needs the hardware.
- **A known unknown:** if a machine-installed printer turns out to be invisible to the
  background account, the fallbacks are to run the print step under a different process, or to
  move the shop to a network printer. Recorded now so the discovery is not a crisis.

### Consequential test cases
- A test receipt printed **from the server process** while nobody is signed in at the console.
- A sale completes, and its receipt prints, with the owner signed out.
- Printer switched off mid-sale: the sale still completes, the PDF fallback appears, and an Admin-visible notice is raised.
- Reprint of an earlier invoice produces the same content as the original.
- An 80mm receipt with a long shop name and address wraps rather than truncating (Phase 3 regression).
