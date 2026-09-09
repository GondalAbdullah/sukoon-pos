# 0006 — Which Document Wins

Status: **Accepted**
Date: 2026-09-08
Phase: 0 (grill-with-docs session 1)

## Context

Four documents govern this project, and they overlap. When they disagree — and they
already do — an implementer needs a rule rather than a judgement call, otherwise the
same argument gets re-run at every phase and gets settled differently each time.

The conflicts are not hypothetical. Two were found before any code was written:

- The Design System (12) mandates PIN quick-switch login and says it *replaces* any
  username/password assumption. The Development Specification (Phase 1) specifies
  hashed passwords and session auth.
- The Design System says the Sale Complete screen "offers an auto-advance countdown"
  (6, Figure 8), while the prototype it names as the interaction reference (10.5)
  implements no such thing.

The Design System's own 0 claims that it "governs anything visual; the Development
Specification governs anything architectural" — a sound principle, but it does not
say which wins when a visual decision has architectural consequences, which is
exactly what the login conflict is.

## Decision

Authority is ordered, and the order is explicit.

| Rank | Document | Authoritative for |
|---|---|---|
| 1 | `/docs/context.md` and `/docs/adr/` | Everything already decided. A recorded decision beats any source document. |
| 2 | **Development Specification** | **All technical and functional matters.** Data model, business rules, security, architecture, phasing, testing, packaging. |
| 3 | **Design System document** | Visual and interaction design only. Colour, type, spacing, layout, copy tone, screen composition, motion. |
| 4 | `sukoon_prototype.html` | A visual and interaction reference for how a screen should look and feel. Its CSS values are the literal source of truth for colour, radius, and shadow. |

Stated plainly, as directed by the client on 2026-09-08: **the Development
Specification is the main source of truth for all technical details. The prototype
and the Design System are for style and UI/UX.**

### The rules that follow

1. **A conflict is never resolved silently.** It is raised, decided, and recorded as
   an ADR. The losing document is not edited to match; the ADR records that it was
   overruled and why.
2. **The prototype is a reference, not a specification.** Where it and the Design
   System disagree on behaviour, the Design System wins. Where the prototype shows a
   *value* (a hex code, a radius, a shadow), the prototype wins, because those were
   authored there first.
3. **The prototype's omissions are not decisions.** It shows only whole-number
   quantities; that is not a ruling that fractional quantities do not exist. Absence
   from the prototype means undesigned, not disallowed.
4. **Neither design document may create technical scope.** A feature that appears
   only in a mock — the loyalty discount, the second-terminal health check — is a
   question to raise, not a requirement to implement. This is Operating Rule 13.
5. **The design Definition of Done still fully applies.** Ranking the Development
   Specification above the Design System does not weaken the design DoD (Design
   System 13); both gates must pass for a phase to close.

## Alternatives Considered

- **Design System wins on anything it covers** — rejected. It is a UI document
  written from mockups, and taken literally it would set security policy through a
  login screen sketch.
- **Newest document wins** — rejected. Recency is not authority, and these documents
  are near-contemporaneous.
- **Resolve each conflict ad hoc as it arises** — rejected. That is what produces
  inconsistent answers to the same question across phases, and it leaves no trace of
  why any of them were chosen.
- **Rewrite the two documents into one merged specification** — rejected for now.
  Genuinely tempting, but it would fork the client's own documents and make future
  updates from them ambiguous. **Trigger for revisiting:** if more than five
  conflicts accumulate, the merge becomes cheaper than the arbitration.

## Consequences

**Easier:** every future conflict has a defined resolution path and an audit trail.
An implementer never has to guess which document to obey.

**Harder:** conflicts must be surfaced and written up rather than quietly resolved,
which costs a little time each occurrence.

**Forecloses:** nothing. The ranking can be superseded by a later ADR.
