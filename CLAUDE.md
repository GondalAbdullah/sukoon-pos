# Sukoon — Project Instructions

Sukoon is a single-store inventory and POS system for Al-Rehman General Store.
Nothing important lives in chat history — a new conversation should read the
following before doing anything else.

## Read first, every session

1. **`docs/context.md`** — current phase, status, open questions, and a full
   session changelog. This is the single source of truth. Read it before touching
   anything.
2. **`docs/adr/`** — one file per real decision, numbered sequentially. Treat an
   **Accepted** ADR as binding. If new work would contradict one, stop and flag it —
   never silently override it (Development Spec, Section 14, step 8).
3. **`docs/glossary.md`** — domain terms as they've been defined. Check before
   guessing what a term means; add new ones the moment they're introduced.

## Governing documents (also in `docs/`)

- **`AsCode_POS_Development_Specification(1).pdf`** — the technical source of truth:
  architecture, features, phases, testing, packaging.
- **`Sukoon_Design_System.pdf`** + **`docs/design/sukoon_prototype.html`** — visual
  and interaction reference only. Per **ADR-0006**, the Development Specification
  outranks these on anything technical; the prototype's CSS values (colour, radius,
  shadow) are literal source of truth for style, and its omissions are not
  decisions.
- **`Building-Software-The-Right-Way.pdf`** — the engineering standards this
  project holds itself to: two-tier testing, honest reporting of mistakes, null
  over a guessed value, isolation and secret-handling discipline.

## Non-negotiable rules (Development Spec, Section 2 — abbreviated, read the full list there)

- Never skip a scheduled `grill-with-docs` session on a flagged decision.
- Never proceed past a 🛑 STOP AND ASK gate without human approval recorded in
  `context.md`.
- Every irreversible or costly-to-reverse decision gets an ADR before it's built,
  not after.
- No feature ships without tests, written alongside it, not after.
- Money and quantity are always fixed-point integers (paisa, milli-units) — never
  floats.
- `context.md` is updated at the end of every work session, not just every phase.

## Starting a new session

Read `docs/context.md`'s "Current phase and status" and the most recent session
changelog entry, then continue from its stated "Next action". Do not re-ask a
question already resolved in an Accepted ADR.
