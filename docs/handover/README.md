# Handover — what goes to the shop, and what must not

## Upgrading a shop already running 1.1.0 (the client's case, as of 2026-10-29)

Send these:

| Item | Where it is |
|---|---|
| `Sukoon-Setup-1.2.0.exe` | built on the Windows VM at `dist\installer\`; a copy in the developer's `dist/installer/` (gitignored). SHA-256 `1caf906bbbd0389ce515fcf38dcb5163d6e1d035462dec61bdf9937a0ae061ff` |
| **The upgrade sheet** | **[Sukoon-Upgrade-to-1.2.0.pdf](Sukoon-Upgrade-to-1.2.0.pdf)**, 2 pages: what's new, **stock must be entered before items sell**, the steps (incl. Settings → Shop details and a test print with width rulers), importing the product list, and what to do if it fails. Source: [upgrade-to-1.2.0.html](upgrade-to-1.2.0.html); `node docs/handover/render-upgrade.js` |
| **The owner's manual** | **[Sukoon-Owner-Manual.pdf](Sukoon-Owner-Manual.pdf)**: updated for 1.2.0 (import, paisa, the till's stock rule and pick list, the receipt and Shop details). Worth resending. |
| The prepared product list | `docs/import/sukoon-products-import.csv` — **on the developer's machine only** (the repository is public). Regenerate with `python scripts/prepare_product_import.py Grocery_Items_list.csv docs/import/sukoon-products-import.csv --categories docs/import/category-mapping.csv` |

A shop still on **1.0.0** can go straight to 1.2.0 (both migrations run); send the 1.1.0 sheet's
"reprint the recovery sheet" step too — [Sukoon-Upgrade-to-1.1.0.pdf](Sukoon-Upgrade-to-1.1.0.pdf).

## What to take on install day

| Item | Where it is |
|---|---|
| `Sukoon-Setup-1.2.0.exe` | built on the Windows VM at `dist\installer\` |
| The install checklist | [install-checklist.md](install-checklist.md) — print it |
| **The owner's manual** | **[Sukoon-Owner-Manual.pdf](Sukoon-Owner-Manual.pdf)** — the single document the client is sent. 32 pages, install to daily use. Source: [sukoon-owner-manual.html](sukoon-owner-manual.html) |
| The owner's guide | [owner-guide.md](owner-guide.md) — print it and leave it at the counter |
| The shop's Cloudflare keys | from the owner's own Cloudflare account, typed into Sukoon on the day |

**Since 2026-09-23 the owner installs Sukoon himself** (the go-live meeting was postponed —
context.md, session 35). The manual above is written for that: it covers the install checklist's
steps in plain language. Two items still need someone with the router password and the printer in
front of them — the router reservation and O-25.

To regenerate the PDF after editing `sukoon-owner-manual.html`:

```bash
node docs/handover/render-manual.js   # writes Sukoon-Owner-Manual.pdf
```

## What the shop ends up holding

| Thing | Where it lives | If it is lost |
|---|---|---|
| The shop's data | `C:\ProgramData\Sukoon\sukoon.db` | restore from a backup in `…\backups\`, or from the offsite copy |
| Local backups | `C:\ProgramData\Sukoon\backups\` | the offsite copies remain |
| **The backup recovery sheet** | **printed, kept away from the shop** | the offsite backups can never be opened — by anyone |
| The Cloudflare access key and secret | the owner's Cloudflare account; the secret is also stored encrypted on the shop PC | make a new token in Cloudflare and paste it into Settings |
| Two Admin passwords | in the owners' heads | **there is no self-service reset** — this is why there must be two Admins (ADR-0040) |
| The WhatsApp key | not set yet (O-23) | re-paste from the Meta account |

## What the developer keeps, and hands over at the end of the engagement

- The source repository and this documentation
- A copy of the recovery sheet **only while the engagement lasts**, then destroyed or handed over
- The Windows VM used to build the installer, with its snapshots

## What must never leave the shop PC

- The recovery sheet must not be photographed, emailed or put in WhatsApp
- The data folder is readable only by administrators and the Sukoon account; don't loosen it
- Nobody needs the `SukoonService` account password — it is random and nobody ever types it

## What is switched off at handover

- **WhatsApp messages** — until the owner's Meta Business account exists and one real message has
  been sent and confirmed (O-23)
- **Automatic receipt printing** — until the shop's printer is chosen in Settings and a test receipt
  comes out (O-25)

## Where the reasoning lives

Every decision is in `docs/adr/`, numbered, with what was rejected and why. The running state of the
project — what is done, what is open, what is believed but unproven — is `docs/context.md`. Start
there.
