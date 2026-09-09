# Sukoon

Inventory management and point-of-sale system for Al-Rehman General Store.
Single-store, offline-first, Windows-installable. See `CLAUDE.md` and `docs/`
for the full project context — this file is only setup steps.

## Setup

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste into .env as SECRET_KEY
```

## Running the app

```bash
source .venv/bin/activate
flask --app sukoon.app run
```

Serves a placeholder page at `http://127.0.0.1:5000/` — the real Login screen
arrives in Phase 1.

## Running the tests

```bash
source .venv/bin/activate
./scripts/run_tests.sh
```

Runs `ruff check` and the full `pytest` suite with coverage. This is the same
check that gates every phase before it can be called done.
