# Sukoon

A single-store inventory management and point-of-sale system for a general
store, built to install and run like an ordinary Windows program on the shop's
own PC — offline-first, no cloud dependency, no internet required for any core
operation. Cashiers ring up sales by barcode scan or by manually entered
weight/amount for loose goods; the shop's owner tracks stock, credit customers
(*Khata*), and daily performance from the same install.

> **This project is being built in the open as a documented, decision-trail-driven
> engineering exercise.** The repository is public for review purposes; see
> [LICENSE](LICENSE) — it is not open source.

## Project status

**Phase 2 (Inventory & Product Management) is built, awaiting sign-off.** On top of
the Phase 1 data model + auth: category/product CRUD, auto-generated SKUs, stock
movements with a full audit trail, barcode assignment + internal Code 128
generation, an A4 label-sheet PDF, and low-stock alerting. The project follows a
phased build plan with an explicit Definition of Done and a human sign-off gate at
the end of each phase — see [`docs/context.md`](docs/context.md) for exactly where
things stand right now, what's been decided, and what's still open.

## If you're reviewing this

The most useful thing in this repository isn't the code yet — Phase 0 is
intentionally just a skeleton. It's the **decision trail**:

- **[`docs/context.md`](docs/context.md)** — single source of truth. Current
  phase, every decision made so far with links to why, open questions, a full
  session-by-session changelog, and a running edge-case/test matrix.
- **[`docs/adr/`](docs/adr/)** — one file per real technical decision (numbered,
  Architecture Decision Records), each recording the context that forced the
  decision, what was chosen, what alternatives were rejected and why, and the
  consequences. Several record a genuine correction — a mistake found and fixed
  in the open, not edited away quietly.
- **[`docs/glossary.md`](docs/glossary.md)** — domain terms as they were
  introduced, so "Khata" or "milli-unit" or "step-up authentication" are
  defined once, precisely, rather than assumed.
- **[`CLAUDE.md`](CLAUDE.md)** — the standing instructions a fresh AI coding
  session reads before touching anything: read `context.md` first, treat an
  Accepted ADR as binding, never proceed past a sign-off gate without recorded
  approval. This project is built with heavy AI assistance (commits are
  co-authored accordingly), governed by an explicit process rather than ad hoc
  prompting — the three governing specification/standards documents this
  process is built from are also in `docs/`.

If you only have five minutes: read `docs/context.md`'s "Current phase and
status" section, then skim the ADR list.

## Setup

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste into .env as SECRET_KEY
```

Then create the database and (optionally) load local dev data:

```bash
export FLASK_APP=sukoon.app        # Windows: set FLASK_APP=sukoon.app
flask db upgrade                   # apply migrations to an empty database
flask seed                         # permissions + a dev Admin/Cashier + sample catalogue
```

`flask seed` reads `SEED_ADMIN_PASSWORD` / `SEED_CASHIER_PASSWORD` from `.env`;
without them it uses a placeholder and logs a warning. `flask seed --no-sample`
loads only the permission catalogue (which every environment needs).

## Running the app

```bash
source .venv/bin/activate
flask --app sukoon.app run
```

Serves a placeholder page at `http://127.0.0.1:5000/`; the sign-in form is at
`/login`. The fully styled Login screen (Tailwind) arrives in a later phase.

## Running the tests

```bash
source .venv/bin/activate
./scripts/run_tests.sh
```

Runs `ruff check` and the full `pytest` suite with coverage — the same check
that gates every phase before it can be called done, and the same check
[GitHub Actions](.github/workflows/ci.yml) runs on every push.

## Stack

Python 3.11+ / Flask / SQLAlchemy / SQLite, server-rendered with
htmx + Alpine.js + Tailwind CSS, packaged for Windows with PyInstaller + Inno
Setup. Every choice is recorded with its reasoning and rejected alternatives in
[ADR-0001](docs/adr/0001-technology-stack.md).
