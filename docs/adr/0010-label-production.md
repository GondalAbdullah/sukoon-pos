# 0010 — Label Production

Status: **Accepted**
Date: 2026-09-09
Phase: 0 (grill-with-docs session 1)
Depends on: [ADR-0009](0009-multiple-barcodes-per-product.md)
Resolves: O-14

## Context

Two situations need a barcode label that the manufacturer did not provide:

1. **Goods with no barcode at all** — loose atta, sugar, daal, repacked or unbranded
   items. Already in scope: Development Specification 6.C requires "Barcode/QR
   generation and assignment per product", and `python-barcode` and `qrcode` are in
   the stack for it.
2. **Relabelled near-expiry units** carrying a price override (ADR-0009).

The question was whether this requires buying a dedicated barcode label printer.

Confirmed with the client on 2026-09-09: **relabelling happens rarely.**

## Decision

**Sukoon generates a printable A4 label sheet as a PDF. The shop prints it on
adhesive sticker sheets using any ordinary office printer.** No dedicated label
printer is purchased.

- Barcode images are generated with `python-barcode`, laid out onto an A4 sheet with
  ReportLab. Both are already in the stack for other reasons; no new dependency.
- The output is an ordinary PDF. Sukoon does not talk to the label printer, does not
  need a driver, and does not care what printer is used.
- Sheet geometry (labels per row, margins) is a setting, so a different brand of
  sticker sheet does not require a code change.

This covers both situations with one feature.

## Alternatives Considered

- **A dedicated thermal label printer** — rejected for now, purely on cost against
  frequency. Relabelling is rare, so peel-and-stick convenience does not justify a
  hardware purchase. **Trigger for revisiting:** label printing becoming a daily
  routine — a spice or dry-goods section labelled every morning, or regular clearance
  runs. At that volume the printer pays for itself and this ADR should be superseded.
- **Printing barcodes on the existing thermal receipt printer** — rejected as the
  default. It is genuinely free and `python-escpos` supports it, but the output is a
  paper strip needing tape, and **thermal paper fades** over weeks in heat. Acceptable
  for a short clearance batch, unacceptable for a permanent label on a sack of atta.
  Kept in mind as a fallback if no ordinary printer is available.
- **No labels at all — the cashier picks the reduced price at the till** — rejected.
  Zero hardware, but it depends on the cashier noticing a marker dot and choosing
  honestly, and it puts a price-changing control back on the till, which is exactly
  what relabelling exists to avoid.

## Consequences

**Easier:** no new hardware, no printer driver, no device-specific code. The same
feature serves both unbranded goods and relabelled units. Output is a PDF, so it can
be previewed, reprinted, or emailed.

**Harder:** peeling stickers off an A4 sheet is manual, and a partly-used sheet
wastes labels. Fine at low volume; irritating at high volume, which is what the
trigger above watches for.

**Forecloses:** nothing. A label printer can be added later as an alternative output.

## Consequential test cases

- A generated barcode image decodes back to the code it was generated from
- A label sheet PDF renders the expected number of labels per page
- Sheet geometry is configurable without a code change
- A product with no barcode can be assigned a generated one and then resolves at the till
