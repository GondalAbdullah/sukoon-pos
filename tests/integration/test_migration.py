"""Migration up/down from an empty database (Development Specification Phase 1
Required Tests; ADR-0016 consequential test).

Driven through the real ``flask db`` CLI in a subprocess, against a throwaway
database file, so this also proves the DoD claim that migrations are reproducible
"with no manual steps".
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "category", "credit_ledger_entry", "customer", "invoice_counter",
    "message_daily_count", "statement_run", "notification_queue", "payment",
    "permission", "product", "product_barcode",
    "refund", "refund_item",
    "role_permission", "sale", "sale_item", "setting", "stock_movement", "user",
}


def _flask(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "FLASK_APP": "sukoon.app",
        "FLASK_ENV": "development",
        "SECRET_KEY": "migration-test-only",
        "DATABASE_PATH": str(db_path),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "flask", "db", *args],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows}


@pytest.mark.slow
def test_migration_roundtrips_from_an_empty_database(tmp_path):
    db_path = tmp_path / "roundtrip.db"

    _flask(db_path, "upgrade")
    after_up = _tables(db_path)
    assert EXPECTED_TABLES <= after_up

    _flask(db_path, "downgrade", "base")
    after_down = _tables(db_path)
    assert after_down & EXPECTED_TABLES == set()

    _flask(db_path, "upgrade")
    assert EXPECTED_TABLES <= _tables(db_path)


@pytest.mark.slow
def test_existing_customers_migrate_as_not_opted_in_and_downgrade_survives_test_sends(tmp_path):
    # ADR-0028 §2: agreement is never assumed retroactively. ADR-0033 §10: a test send
    # has no customer, and the downgrade must not choke on it.
    db_path = tmp_path / "phase5.db"
    _flask(db_path, "upgrade", "58f3a01f76d8")  # the schema before Phase 5
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO customer (name, balance_paisa, phone_verified, is_active, "
                "created_at) VALUES ('Old Regular', 0, 1, 1, '2026-01-01 00:00:00')")
    con.commit()
    con.close()

    _flask(db_path, "upgrade")
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT whatsapp_opt_in FROM customer").fetchone() == (0,)
    con.execute("INSERT INTO notification_queue (customer_id, notification_type, dedupe_key, "
                "status, attempt_count, created_at) VALUES (NULL, 'test', 'test:1', "
                "'sent', 1, '2026-01-01 00:00:00')")
    con.commit()
    con.close()

    _flask(db_path, "downgrade", "58f3a01f76d8")
    con = sqlite3.connect(db_path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(customer)")}
    assert "whatsapp_opt_in" not in cols
    assert con.execute("SELECT COUNT(*) FROM notification_queue").fetchone() == (0,)
    con.close()
