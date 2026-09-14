# 0024 — Shop Timezone for Displayed Times

Status: **Accepted** 2026-09-14 — chosen by the client
Date: 2026-09-14
Phase: 3 (addendum, after functional sign-off)
Resolves: **O-21**
Depends on: [ADR-0016](0016-consolidated-data-model.md) (UTC timestamps, the yearly invoice counter), [ADR-0001](0001-technology-stack.md) (one host PC, browsers on the LAN)

## Context

Every timestamp is stored as timezone-aware UTC (`models/base.py::utcnow`) — correct,
and not in question. But every place a time is *shown* formatted it with a bare
`strftime`, so the stock movement history, the pending-refunds list and the
**printed and PDF receipt** all read UTC. Pakistan is UTC+5 with no daylight saving,
so a 6:54 pm sale printed as 13:54. Found in session 21 from the developer's own
walkthrough (stock history said 00:50 for a sale made at 05:50).

The same root cause reaches one place that is not display: `claim_invoice_number`
takes the invoice year from `datetime.now(UTC).year`. Between 00:00 and 05:00 on
1 January, Pakistan is already in the new year while UTC is not — the first sales
of the year would be numbered `INV-<last year>-…`, and the counter would reset five
hours late (ADR-0016: "resets on the first sale of a new calendar year" — the shop's
calendar, not Greenwich's).

## Decision

**One fixed shop timezone, not each PC's Windows setting.**

1. Storage is unchanged: UTC everywhere.
2. A setting `shop.timezone` holds an IANA zone name, defaulting to
   **`Asia/Karachi`** when unset. No UI yet (Settings is a later phase); the default
   is the right answer for this shop.
3. Conversion happens once, in `sukoon/services/clock.py`: `to_shop_time(dt)` treats
   a naive datetime as UTC (SQLite returns naive values even for aware writes) and
   converts to the shop zone. An unknown zone name in the setting falls back to
   `Asia/Karachi` with a logged warning — a typo must not take the till down.
4. Every displayed time goes through it: a `shop_time` Jinja filter for templates,
   and `build_receipt` converts before either renderer sees the time.
5. The invoice year is the **shop-time** year.
6. `tzdata` is added as a runtime dependency. Windows has no system IANA database,
   so `zoneinfo` cannot find `Asia/Karachi` in the packaged installer without it
   (it happens to work on the Linux dev machine, which is exactly how this would
   have shipped broken).

## Alternatives Considered

- **Follow the host PC's Windows timezone.** No setting to maintain. Lost because
  second-hand and imported PCs routinely ship set to the wrong zone, and nothing in
  Sukoon would notice — every receipt would be wrong, silently. Under ADR-0001 the
  host PC does all formatting for every till, so one misconfigured machine is
  enough. A fixed setting makes the shop's clock a property of the shop.
- **Convert in the browser (JavaScript, each viewer's zone).** Lost on three counts:
  receipts are rendered server-side (ESC/POS bytes and PDF) so they would still need
  a server rule; two tills with different zones would disagree about the same sale;
  and it would scatter formatting across templates.
- **Store local time instead of UTC.** Rejected outright: it would make every
  existing row ambiguous and complicate any future sync or report across a
  (hypothetical) DST-observing zone.

## Consequences

- **Easier:** receipts, history and approvals all read the time on the shop wall,
  from any till, whatever the PC is set to. The invoice year turns over at the
  shop's midnight.
- **Harder:** a new place that shows a time must use `shop_time` / `to_shop_time`;
  a bare `strftime` on a stored timestamp is now a bug. (Enforceable by review; not
  worth a lint rule yet at three call sites.)
- **Not solved here, and cannot be by any setting:** a PC whose *clock* is wrong.
  Timezone and clock accuracy are different things. The installer notes should tell
  the owner to turn on Windows' "Set time automatically".
- **Forecloses nothing:** a Settings screen can expose `shop.timezone` later with no
  data change.

### Consequential test cases
- A naive and an aware UTC datetime both convert to Asia/Karachi (+5:00).
- An invalid `shop.timezone` falls back to Asia/Karachi rather than raising.
- A receipt for a sale at 14:30 UTC reads 19:30.
- A sale at 2026-12-31 20:00 UTC (01:00 on 1 January in Pakistan) is numbered
  `INV-2027-0001`.
