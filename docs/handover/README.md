# Handover — what goes to the shop, and what must not

## What to take on install day

| Item | Where it is |
|---|---|
| `Sukoon-Setup-1.0.0.exe` | built on the Windows VM at `dist\installer\` |
| The install checklist | [install-checklist.md](install-checklist.md) — print it |
| The owner's guide | [owner-guide.md](owner-guide.md) — print it and leave it at the counter |
| The shop's Cloudflare keys | from the owner's own Cloudflare account, typed into Sukoon on the day |

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
