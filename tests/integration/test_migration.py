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


@pytest.mark.slow
def test_a_customer_with_sales_and_payments_survives_a_customer_table_rebuild(tmp_path):
    """SQLite adds a column with a foreign key by rebuilding the table, and Sukoon turns on
    foreign-key enforcement for every connection. With sales, payments and ledger entries
    pointing at a customer, dropping the old ``customer`` table was refused and the 1.1.0
    upgrade failed on real data (the startup backup put everything back). Earlier migration
    tests only ever had customers nothing pointed at."""
    db_path = tmp_path / "shop.db"
    _flask(db_path, "upgrade", "de48cca91869")  # the schema 1.0.0 shipped
    con = sqlite3.connect(db_path)
    con.executescript("""
        PRAGMA foreign_keys = ON;
        INSERT INTO user (id, name, initials, role, password_hash, is_active,
                          failed_login_attempts, created_at)
            VALUES (1, 'Owner', 'OW', 'admin', 'x', 1, 0, '2026-09-20 10:00:00');
        INSERT INTO customer (id, name, balance_paisa, phone_verified, whatsapp_opt_in,
                              is_active, created_at)
            VALUES (1, 'Ali Raza', 40000, 1, 0, 1, '2026-09-20 10:00:00');
        INSERT INTO sale (id, invoice_number, customer_id, user_id, subtotal_paisa,
                          discount_paisa, tax_paisa, total_paisa, payment_method, status,
                          created_at)
            VALUES (1, 'INV-2026-000001', 1, 1, 60000, 0, 0, 60000, 'credit', 'completed',
                    '2026-09-20 10:05:00');
        INSERT INTO payment (id, customer_id, amount_paisa, method, received_by_user_id,
                             created_at)
            VALUES (1, 1, 20000, 'cash', 1, '2026-09-21 10:00:00');
        INSERT INTO credit_ledger_entry (customer_id, entry_type, amount_paisa,
                                         balance_after_paisa, sale_id, created_by_user_id,
                                         created_at)
            VALUES (1, 'credit_sale', 60000, 60000, 1, 1, '2026-09-20 10:05:00');
        INSERT INTO credit_ledger_entry (customer_id, entry_type, amount_paisa,
                                         balance_after_paisa, payment_id, created_by_user_id,
                                         created_at)
            VALUES (1, 'payment', -20000, 40000, 1, 1, '2026-09-21 10:00:00');
    """)
    con.commit()
    con.close()

    _flask(db_path, "upgrade")  # raises on a non-zero exit, with flask's output
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT name, label, balance_paisa FROM customer").fetchall() == [
        ("Ali Raza", None, 40000)]
    assert con.execute("SELECT COUNT(*) FROM credit_ledger_entry WHERE customer_id = 1"
                       ).fetchone() == (2,)
    assert con.execute("SELECT customer_id FROM sale").fetchone() == (1,)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()

    _flask(db_path, "downgrade", "de48cca91869")
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM customer").fetchone() == (1,)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
