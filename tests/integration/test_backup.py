"""Local backups (ADR-0037 §2–3): consistent snapshots while selling, restore, and retention."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from sukoon import backup

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def _shop_db(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE sale (id INTEGER PRIMARY KEY, total INTEGER)")
    con.commit()
    return con


def _sales(path):
    """How many sales the file holds — None if it doesn't even have the table."""
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM sale").fetchone()[0]
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def test_a_snapshot_includes_sales_still_in_the_write_ahead_log(tmp_path):
    """Why the backup API and not a file copy: in WAL mode recent sales live in the -wal file,
    and a copy of the main file alone loses them."""
    db = tmp_path / "sukoon.db"
    con = _shop_db(db)
    con.execute("PRAGMA wal_autocheckpoint=0")  # the shop's latest sales, not yet checkpointed
    con.executemany("INSERT INTO sale (total) VALUES (?)", [(i,) for i in range(50)])
    con.commit()
    try:
        naive = tmp_path / "file-copy.db"
        shutil.copyfile(db, naive)
        # the trap this module exists to avoid — worse than first expected: the copy hasn't
        # lost only the sales, it hasn't got the table, which was also still in the log
        assert _sales(naive) is None

        snap = backup.snapshot(db, tmp_path / "backups" / "snap.db")
        assert _sales(snap) == 50
    finally:
        con.close()


def test_there_is_nothing_to_back_up_and_nothing_gets_created(tmp_path):
    missing = tmp_path / "sukoon.db"
    with pytest.raises(backup.BackupError, match="no database"):
        backup.snapshot(missing, tmp_path / "b.db")
    assert not missing.exists() and not (tmp_path / "b.db").exists()


def test_a_damaged_database_is_not_passed_off_as_a_backup(tmp_path):
    db = tmp_path / "sukoon.db"
    db.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4000)
    with pytest.raises(backup.BackupError):
        backup.snapshot(db, tmp_path / "backups" / "b.db")
    assert list((tmp_path / "backups").glob("*")) == []  # no .partial left behind


def test_restore_puts_the_backup_back_and_discards_the_abandoned_log(tmp_path):
    db = tmp_path / "sukoon.db"
    con = _shop_db(db)
    con.execute("INSERT INTO sale (total) VALUES (100)")
    con.commit()
    con.close()
    snap = backup.snapshot(db, tmp_path / "snap.db")

    con = sqlite3.connect(db)
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.executemany("INSERT INTO sale (total) VALUES (?)", [(1,), (2,), (3,)])
    con.commit()
    con.close()
    (tmp_path / "sukoon.db-wal").write_bytes(b"stale log from the abandoned state")

    backup.restore(snap, db)
    assert _sales(db) == 1 and not (tmp_path / "sukoon.db-wal").exists()


def test_a_scheduled_backup_is_kept_only_when_the_data_changed(tmp_path):
    db, backups = tmp_path / "sukoon.db", tmp_path / "backups"
    _shop_db(db).close()

    first = backup.run_scheduled(db, backups, NOW)
    assert first.path is not None and not first.unchanged
    quiet = backup.run_scheduled(db, backups, NOW + timedelta(minutes=15))
    assert quiet.unchanged and quiet.path is None  # overnight: no pile of identical copies

    con = sqlite3.connect(db)
    con.execute("INSERT INTO sale (total) VALUES (590)")
    con.commit()
    con.close()
    busy = backup.run_scheduled(db, backups, NOW + timedelta(minutes=30))
    assert busy.path is not None and _sales(busy.path) == 1
    assert len(list(backups.glob("sukoon-*.db"))) == 2
    assert not list(backups.glob("*.candidate*"))


def test_retention_keeps_a_day_in_full_then_one_a_day_for_fourteen_days(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    made = []
    for hours_ago in range(0, 24 * 20, 6):  # every 6 hours for 20 days
        stamp = NOW - timedelta(hours=hours_ago)
        path = backups / backup.scheduled_name(stamp)
        path.write_bytes(b"x")
        made.append((stamp, path))
    upgrade = backups / backup.pre_upgrade_name(NOW - timedelta(days=60), "a", "b")
    upgrade.write_bytes(b"x")

    backup.prune(backups, NOW)

    left = {p for _, p in made if p.exists()}
    recent = {p for s, p in made if s >= NOW - timedelta(hours=24)}
    assert recent <= left                                   # the last day, untouched
    older_days = {s.date() for s, p in made if p in left and s < NOW - timedelta(hours=24)}
    assert len(older_days) == 14                             # one per day, fourteen days
    assert len(left) == len(recent) + 14
    for day in older_days:                                   # and it's that day's newest
        of_day = [(s, p) for s, p in made if s.date() == day and s < NOW - timedelta(hours=24)]
        assert max(of_day)[1] in left
    assert upgrade.exists()                                  # pre-upgrade: never pruned


def test_status_says_when_the_last_backup_worked_and_what_last_failed(tmp_path):
    backup.record_status(tmp_path, NOW, ok=True)
    assert backup.read_status(tmp_path)["last_ok_at"] == NOW.isoformat()
    backup.record_status(tmp_path, NOW + timedelta(minutes=15), ok=False, error="disk full")
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["last_error"] == "disk full" and status["last_ok_at"] == NOW.isoformat()
    backup.record_status(tmp_path, NOW + timedelta(minutes=30), ok=True)
    assert backup.read_status(tmp_path)["last_error"] is None


def test_an_unreadable_status_file_reads_as_no_status(tmp_path):
    (tmp_path / "status.json").write_text("{not json", encoding="utf-8")
    assert backup.read_status(tmp_path) == {}
