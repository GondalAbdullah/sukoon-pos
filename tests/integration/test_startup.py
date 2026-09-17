"""Starting an installed Sukoon (ADR-0035, ADR-0036, ADR-0038 §7, §11): the data folder,
a migration that is backed up first and undone if it fails, and the real launcher."""
from __future__ import annotations

import logging
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sukoon import startup
from sukoon.extensions import db
from sukoon.models import Permission
from sukoon.services.permissions import PERMISSIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_3 = "58f3a01f76d8"  # an older release's schema
NOW = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


def _installed(tmp_path):
    return startup.build_app("production", environ={"SUKOON_DATA_DIR": str(tmp_path / "data")})


def _tables(path):
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def test_production_points_everything_at_the_data_folder(tmp_path):
    app = _installed(tmp_path)
    data = tmp_path / "data"
    assert app.config["DATA_DIR"] == str(data)
    assert app.config["SQLALCHEMY_DATABASE_URI"] == f"sqlite:///{data / 'sukoon.db'}"
    for key, name in [("LOG_DIR", "logs"), ("BACKUP_DIR", "backups"),
                      ("WHATSAPP_KEY_PATH", "whatsapp.key"),
                      ("WORKER_LOCK_PATH", "sukoon-worker.lock")]:
        assert app.config[key] == str(data / name)
    assert app.config["SECRET_KEY"] == (data / "secret.key").read_text(encoding="ascii")
    assert _installed(tmp_path).config["SECRET_KEY"] == app.config["SECRET_KEY"]  # kept


def test_development_never_touches_a_data_folder(tmp_path):
    app = startup.build_app("development", environ={"SUKOON_DATA_DIR": str(tmp_path / "data")})
    assert "DATA_DIR" not in app.config and not (tmp_path / "data").exists()


def test_a_new_install_gets_the_whole_schema_and_its_permissions(tmp_path):
    app = _installed(tmp_path)
    assert startup.prepare_database(app, NOW) is None  # nothing existed, nothing to back up
    assert {"sale", "customer", "notification_queue", "alembic_version"} <= \
        _tables(tmp_path / "data" / "sukoon.db")
    with app.app_context():
        assert db.session.query(Permission).count() == len(PERMISSIONS)


def test_starting_again_on_a_current_database_takes_no_backup(tmp_path):
    app = _installed(tmp_path)
    startup.prepare_database(app, NOW)
    assert startup.prepare_database(app, NOW) is None
    assert not list((tmp_path / "data" / "backups").glob("pre-upgrade-*"))


def _at_phase_3(tmp_path):
    app = _installed(tmp_path)
    with app.app_context():
        from flask_migrate import upgrade

        upgrade(directory=str(startup.migrations_dir()), revision=PHASE_3)
        db.session.execute(db.text(
            "INSERT INTO category (name, display_order, is_active) "
            "VALUES ('Groceries', 0, 1)"))
        db.session.commit()
        db.session.remove()
        db.engine.dispose()
    return app


def test_an_upgrade_is_backed_up_first_and_then_applied(tmp_path):
    app = _at_phase_3(tmp_path)
    taken = startup.prepare_database(app, NOW)

    assert taken is not None and taken.parent == tmp_path / "data" / "backups"
    assert taken.name.startswith("pre-upgrade-") and PHASE_3 in taken.name
    assert "statement_run" not in _tables(taken)          # the backup is the Phase 3 schema
    assert "statement_run" in _tables(tmp_path / "data" / "sukoon.db")  # upgraded to Phase 5
    with app.app_context():
        assert db.session.execute(db.text("SELECT name FROM category")).scalar() == "Groceries"


def test_a_failed_upgrade_puts_the_backup_back_and_refuses_to_start(tmp_path, monkeypatch):
    app = _at_phase_3(tmp_path)
    db_file = tmp_path / "data" / "sukoon.db"
    before = _tables(db_file)

    def half_a_migration(directory):
        con = sqlite3.connect(db_file)  # changes land, then it dies part-way
        con.execute("CREATE TABLE half_migrated (id INTEGER)")
        con.execute("DELETE FROM category")
        con.commit()
        con.close()
        raise RuntimeError("simulated failure in the middle of a migration")

    monkeypatch.setattr(startup, "_upgrade", half_a_migration)
    with pytest.raises(startup.StartupError) as err:
        startup.prepare_database(app, NOW)

    message = str(err.value)
    assert "put back the backup" in message and "simulated failure" in message
    assert _tables(db_file) == before                     # the half-migration is gone
    con = sqlite3.connect(db_file)
    try:
        assert con.execute("SELECT name FROM category").fetchone() == ("Groceries",)
    finally:
        con.close()


def test_a_database_with_tables_but_no_version_is_left_untouched(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    con = sqlite3.connect(data / "sukoon.db")
    con.execute("CREATE TABLE sale (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    with pytest.raises(startup.StartupError, match="no record of its schema version"):
        startup.prepare_database(_installed(tmp_path), NOW)
    assert _tables(data / "sukoon.db") == {"sale"}


def test_sukoons_loggers_still_work_after_a_migration_at_start_up(tmp_path):
    """Alembic's env.py reconfigures logging. With its default it disabled every existing
    logger — an installed copy would have stopped writing its log after its first upgrade."""
    app = _installed(tmp_path)
    startup.prepare_database(app, NOW)
    assert not app.logger.disabled
    assert not logging.getLogger("sukoon.startup").disabled
    assert not logging.getLogger("sukoon.jobs.scheduler").disabled


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_the_shipped_launcher_serves_sukoon_from_its_data_folder(tmp_path):
    """End to end, as the shop PC will run it: production config, a fresh data folder,
    migrations at start-up, Waitress — then a real HTTP request."""
    port = _free_port()
    data = tmp_path / "data"
    env = {**os.environ, "SUKOON_CONFIG": "production", "SUKOON_DATA_DIR": str(data),
           "SUKOON_PORT": str(port), "SUKOON_HOST": "127.0.0.1", "WHATSAPP_PROVIDER": "fake",
           "PYTHONPATH": str(REPO_ROOT)}
    env.pop("SECRET_KEY", None)
    proc = subprocess.Popen([sys.executable, "-m", "sukoon.run"], cwd=tmp_path, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline, body, server = time.monotonic() + 60, None, None
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/setup", timeout=2) as r:
                    body, server = r.read().decode(), r.headers.get("Server")
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.3)
        assert proc.poll() is None, proc.stdout.read()
        assert body is not None and "Set up Sukoon" in body
        assert server == "Sukoon"                             # Waitress, not the dev server
        assert (data / "sukoon.db").exists() and (data / "secret.key").exists()
        assert not (tmp_path / "instance").exists()           # nothing written where it started
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.slow
def test_a_port_already_in_use_is_written_to_the_log_not_lost(tmp_path):
    """Under Task Scheduler nobody sees a console: a second copy, or anything else holding the
    port, must leave its reason in the log file."""
    data = tmp_path / "data"
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        env = {**os.environ, "SUKOON_CONFIG": "production", "SUKOON_DATA_DIR": str(data),
               "SUKOON_PORT": str(port), "SUKOON_HOST": "127.0.0.1",
               "WHATSAPP_PROVIDER": "fake", "SUKOON_SCHEDULER": "0",
               "PYTHONPATH": str(REPO_ROOT)}
        proc = subprocess.run([sys.executable, "-m", "sukoon.run"], cwd=tmp_path, env=env,
                              capture_output=True, text=True, timeout=90)
    assert proc.returncode == 3
    log = (data / "logs" / "sukoon.log").read_text(encoding="utf-8")
    assert f"could not serve on 127.0.0.1:{port}" in log


@pytest.mark.slow
def test_a_refusal_to_start_is_written_to_the_log_file(tmp_path):
    """The first Windows build refused to start — correctly — but the reason went only to the
    console. Under Task Scheduler that would have left the shop with tills saying 'can't
    connect' and nothing in the log."""
    data = tmp_path / "data"
    data.mkdir()
    con = sqlite3.connect(data / "sukoon.db")
    con.execute("CREATE TABLE sale (id INTEGER PRIMARY KEY)")  # tables, no schema version
    con.commit()
    con.close()
    env = {**os.environ, "SUKOON_CONFIG": "production", "SUKOON_DATA_DIR": str(data),
           "SUKOON_PORT": str(_free_port()), "SUKOON_SCHEDULER": "0",
           "WHATSAPP_PROVIDER": "fake", "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run([sys.executable, "-m", "sukoon.run"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 2
    log = (data / "logs" / "sukoon.log").read_text(encoding="utf-8")
    assert "Sukoon did not start" in log and "no record of its schema version" in log
