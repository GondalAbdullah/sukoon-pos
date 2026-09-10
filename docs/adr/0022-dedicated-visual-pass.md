# 0022 — A Dedicated Visual Pass After Phase 3

Status: **Accepted** 2026-09-11 — decided by the client
Date: 2026-09-11
Phase: 3 → 4 boundary
Relates to: [ADR-0006](0006-document-authority.md); context.md §4b (the deferral itself)

## Context

Development Specification §5.1 says the visual layer (Tailwind + htmx + Alpine)
changes only *"how templates are written and styled from Phase 1 onward"* and adds
*"no change to any phase in Section 11"* — i.e. every screen is meant to be built
in the Design System's visual language **as its phase builds it**, with no
separate styling phase.

This project deviated. Phases 1–3 shipped **functional HTML** — plain forms that
reload — to get the data model, money arithmetic, auth, and the sale transaction
right before spending effort on pixels. Each deviation is recorded in context.md
§4b (Phase 1 login, Phase 2 stock screens, Phase 3 Till). The consequence is that
the design Definition of Done (Design System §13) has not been met for any phase
so far, and the deferred styling work has accumulated across four screens'
worth of templates.

The client was asked how to spend that work and chose: **one dedicated visual
pass, run after Phase 3 is complete and before Phase 4 begins.**

## Decision

### 1. Phase 3 finishes as functional HTML

The remaining Phase 3 work — provisional-create at the till, the refund flow, the
ESC/POS receipt — is built functional-HTML-first like the rest of the phase. Phase
3's functional Definition of Done is what gates it.

### 2. Then a single visual pass, before Phase 4

A dedicated block of work — call it **Phase 3.5** — that converts every existing
template to the Design System's visual language:

- Login (Figure 1, with the ADR-0008 password deviation)
- Stock list, product detail, product form, bulk entry, categories, Add Stock
  (Figures 3, 7)
- Till, Sale Complete (Figures 2, 8) — including the O-11 loose-goods row and the
  O-9 auto-advance ring from the §4b design mockups
- The refund screen (O-7 policy is set; its pixels are drawn here)
- `base.html` → the persistent nav rail, top bar, flash/toast treatment

Source of truth, in order: the prototype's CSS values are literal for colour,
radius, shadow, spacing (ADR-0006); the nine reference screenshots for layout; the
Design System PDF for interaction rules; the §4b mockups for the two components the
prototype lacks.

Deliverables: `static/css/tailwind.css` compiled and committed (no Node in the
installer — Development Spec §5.1), htmx swaps for the interactions the Design
System calls out (cart panel, per-row stock, bulk-entry focus return), Alpine for
dropdowns / modals / live totals. The two-tier tests written for Phases 1–3 must
still pass unchanged — this pass changes templates and adds a stylesheet, not
routes or services.

### 3. Phases 4–6 are built styled from the start

Once the vocabulary exists (compiled Tailwind, the shared layout, the component
patterns), every new screen from Phase 4 on is built in it directly, as §5.1
always intended. Phase 3.5 is a one-time catch-up, not a new standing practice.

### 4. The design DoD is met at the end of Phase 3.5

Design System §13's side-by-side check against each reference screenshot is
performed once, for all of Phases 1–3, at the close of Phase 3.5 — and per phase
from Phase 4 onward.

## Alternatives Considered

- **Style each screen as its phase builds it (the literal §5.1 approach)** — what
  the spec says. Rejected as already overtaken by events: Phases 1–3 are built
  unstyled, so this would still need a retrofit, just spread thin across Phase 4–6
  work and interleaved with unrelated feature logic.
- **Fold the retrofit into Phase 4–6 incrementally** — a screen's worth of styling
  bolted onto each feature phase. Rejected: it hides the size of the debt, makes
  each phase's DoD ambiguous, and the client would demo unstyled core screens for
  months.
- **Defer all styling to just before Phase 7 packaging** — the last safe point
  (the compiled CSS must be in the installer). Rejected: the client should be
  seeing the real interface well before then, and Insights (Phase 6) is far easier
  to build right if the visual system already exists.
- **Treat it as a formal numbered phase with its own STOP AND ASK gate** —
  rejected as heavier than needed. It is a catch-up on already-agreed design
  references, not a new design decision; §5.1 explicitly attaches no gate to the
  visual layer.

## Consequences

**Easier:** the visual work is one coherent block against one set of references,
not scattered. Phases 4–6 get a real design system to build on. The client sees
the actual product in one step change.

**Harder:** Phase 3's screens get built twice in effect (structure now, style
later), and the design DoD for Phases 1–3 is outstanding until Phase 3.5 closes —
this must stay visible in context.md, not quietly forgotten.

**Forecloses:** nothing. If a later screen needs SPA-level richness that
htmx/Alpine cannot give, that remains a separate scoped-and-ADR'd decision
(Development Spec §5.1).
