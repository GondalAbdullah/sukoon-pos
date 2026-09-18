"""Offsite backup as the shop uses it (ADR-0037): the settings, the scheduled send, the weekly
check, and the recovery sheet."""
from __future__ import annotations

import base64
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon import offsite
from sukoon.jobs import scheduler
from sukoon.services import offsite_service, settings_service
from sukoon.services.notifications import secret_store
from tests.conftest import ADMIN_PASSWORD

NOW = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)


class _Bucket(BaseHTTPRequestHandler):
    store: dict[str, bytes] = {}

    def _name(self):
        return self.path.split("?", 1)[0].split("/books/", 1)[-1]

    def do_PUT(self):  # noqa: N802
        type(self).store[self._name()] = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if "list-type=2" in self.path:
            body = ("<ListBucketResult>" +
                    "".join(f"<Contents><Key>{k}</Key></Contents>" for k in sorted(self.store)) +
                    "</ListBucketResult>").encode()
        else:
            body = self.store.get(self._name())
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self):  # noqa: N802
        type(self).store.pop(self._name(), None)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def bucket():
    _Bucket.store = {}
    httpd = HTTPServer(("127.0.0.1", 0), _Bucket)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def shop(app, tmp_path, bucket):
    """An installed-looking Sukoon: a data folder with a backup in it, and offsite set up."""
    backups = tmp_path / "backups"
    backups.mkdir()
    database = backups / "sukoon-20260918-100000.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sale (id INTEGER PRIMARY KEY)")
    connection.executemany("INSERT INTO sale (id) VALUES (?)", [(i,) for i in range(4)])
    connection.commit()
    connection.close()

    app.config.update(BACKUP_DIR=str(backups),
                      OFFSITE_SECRET_PATH=str(tmp_path / "offsite.key"),
                      BACKUP_KEY_PATH=str(tmp_path / "backup-encryption.key"))
    settings_service.set(offsite_service.ENDPOINT, bucket)
    settings_service.set(offsite_service.BUCKET, "books")
    settings_service.set(offsite_service.ACCESS_KEY_ID, "key-id")
    settings_service.set(offsite_service.ENABLED, "1")
    secret_store.save_key(app.config["OFFSITE_SECRET_PATH"], "the-secret")
    # As the Settings screen does when it is set up: the key is made deliberately, once, and the
    # recovery sheet printed. The scheduled job never invents one — a new key would leave the
    # owner's printed sheet not matching their backups, discovered in a disaster.
    offsite_service.encryption_key(app.config["BACKUP_KEY_PATH"], create=True)
    from sukoon.extensions import db

    db.session.commit()
    return {"backups": backups, "database": database, "app": app, "tmp": tmp_path}


def _paths(shop):
    app = shop["app"]
    return {"backups_dir": app.config["BACKUP_DIR"],
            "secret_path": app.config["OFFSITE_SECRET_PATH"],
            "key_path": app.config["BACKUP_KEY_PATH"]}


# --- sending and checking -----------------------------------------------------------------------

def test_the_newest_backup_goes_offsite_encrypted(shop):
    name = offsite_service.send_latest(**_paths(shop), now=NOW)
    assert name == "sukoon-20260918-100000.db.enc"
    stored = _Bucket.store[f"sukoon/{name}"]
    assert stored.startswith(offsite.MAGIC) and b"SQLite format 3" not in stored


def test_the_same_backup_is_not_sent_twice(shop):
    assert offsite_service.send_latest(**_paths(shop), now=NOW) is not None
    assert offsite_service.send_latest(**_paths(shop), now=NOW) is None


def test_the_weekly_check_brings_it_back_and_opens_it(shop):
    offsite_service.send_latest(**_paths(shop), now=NOW)
    name, sales = offsite_service.check(**_paths(shop), now=NOW)
    assert name == "sukoon-20260918-100000.db.enc" and sales == 4
    assert not (shop["backups"] / "offsite-check.db").exists()   # cleans up after itself


def test_the_check_fails_loudly_when_the_backup_cannot_be_unlocked(shop):
    offsite_service.send_latest(**_paths(shop), now=NOW)
    # the key is lost and a new one made — every backup already offsite stays locked
    (shop["tmp"] / "backup-encryption.key").unlink()
    offsite_service.encryption_key(shop["app"].config["BACKUP_KEY_PATH"], create=True)
    with pytest.raises(offsite.OffsiteError, match="could not be unlocked"):
        offsite_service.check(**_paths(shop), now=NOW)


def test_nothing_set_up_is_not_an_error(app, tmp_path):
    app.config.update(BACKUP_DIR=str(tmp_path), OFFSITE_SECRET_PATH=str(tmp_path / "s.key"),
                      BACKUP_KEY_PATH=str(tmp_path / "b.key"))
    with pytest.raises(offsite_service.NotConfigured):
        offsite_service.send_latest(backups_dir=tmp_path, secret_path=tmp_path / "s.key",
                                    key_path=tmp_path / "b.key", now=NOW)


# --- what an Admin sees ---------------------------------------------------------------------

def test_the_status_says_when_it_last_worked_and_when_it_last_failed(shop):
    offsite_service.send_latest(**_paths(shop), now=NOW)
    state = offsite_service.describe(shop["backups"], shop["app"].config["OFFSITE_SECRET_PATH"])
    assert state.configured and state.enabled and state.last_ok_at == NOW and not state.last_error

    offsite_service.record(shop["backups"], NOW, ok=False, error="no internet")
    state = offsite_service.describe(shop["backups"], shop["app"].config["OFFSITE_SECRET_PATH"])
    assert state.last_error == "no internet"


def test_an_offsite_backup_that_stopped_is_called_stale(shop):
    # measured against the real clock, which is what "stale" means to a shop
    five_hours_ago = datetime.now(UTC) - timedelta(hours=5)
    offsite_service.record(shop["backups"], five_hours_ago, ok=True, object_name="old.enc")
    state = offsite_service.describe(shop["backups"], shop["app"].config["OFFSITE_SECRET_PATH"])
    assert state.stale and state.verification_overdue


# --- the key and its sheet ----------------------------------------------------------------------

def test_the_key_is_made_once_and_then_never_changes(shop):
    path = shop["app"].config["BACKUP_KEY_PATH"]
    first = offsite_service.encryption_key(path, create=True)
    assert offsite_service.encryption_key(path) == first
    assert len(first) == offsite.KEY_BYTES


def test_the_recovery_sheet_prints_the_key_in_readable_groups(shop):
    path = shop["app"].config["BACKUP_KEY_PATH"]
    key = offsite_service.encryption_key(path, create=True)
    printed = offsite_service.recovery_sheet_key(path)
    assert " " in printed and len(printed.split(" ")[0]) == 4
    assert base64.b64decode(printed.replace(" ", "") + "==") == key


def test_the_recovery_sheet_page_warns_where_to_keep_it(client, seeded, login, shop):
    login("Owner", ADMIN_PASSWORD)
    offsite_service.encryption_key(shop["app"].config["BACKUP_KEY_PATH"], create=True)
    page = client.get("/settings/offsite/recovery-sheet")
    assert page.status_code == 200
    assert b"away from the shop" in page.data and b"nobody can" in page.data


# --- the scheduled job ---------------------------------------------------------------------------

def test_the_job_sends_and_records_without_ever_raising(shop, monkeypatch):
    assert scheduler.run_offsite(shop["app"], NOW) == "sukoon-20260918-100000.db.enc"

    def no_internet(*args, **kwargs):
        raise offsite.OffsiteError("The storage service could not be reached: network unreachable")

    monkeypatch.setattr(offsite_service, "send_latest", no_internet)
    assert scheduler.run_offsite(shop["app"], NOW) is None      # a dropped connection is not fatal
    state = offsite_service.describe(shop["backups"], shop["app"].config["OFFSITE_SECRET_PATH"])
    assert "could not be reached" in state.last_error


def test_the_job_does_nothing_when_offsite_is_switched_off(shop):
    settings_service.set(offsite_service.ENABLED, "0")
    from sukoon.extensions import db

    db.session.commit()
    assert scheduler.run_offsite(shop["app"], NOW) is None
    assert _Bucket.store == {}


# --- losing the key, and getting it back (ADR-0037 §5) -------------------------------------------

def _make_unreadable(path):
    """What a reinstalled Windows leaves behind: the file is there, this PC can't unlock it."""
    from sukoon.services.notifications import secret_store

    def refuse(*args, **kwargs):
        raise secret_store.KeyStoreError("Windows could not protect or unprotect the key.")

    return refuse


def test_a_key_this_pc_cannot_unlock_is_explained_not_a_crash(shop, monkeypatch):
    from sukoon.services.notifications import secret_store

    monkeypatch.setattr(secret_store, "load_key", _make_unreadable(None))
    path = shop["app"].config["BACKUP_KEY_PATH"]
    assert offsite_service.key_state(path) == "unreadable"
    with pytest.raises(offsite_service.KeyUnreadable, match="recovery sheet"):
        offsite_service.encryption_key(path)
    with pytest.raises(offsite_service.KeyUnreadable):
        offsite_service.encryption_key(path, create=True)   # never quietly makes a new one


def test_the_printed_sheet_puts_the_same_key_back(shop):
    path = shop["app"].config["BACKUP_KEY_PATH"]
    original = offsite_service.encryption_key(path)
    printed = offsite_service.recovery_sheet_key(path)          # groups of four, as printed

    (shop["tmp"] / "backup-encryption.key").unlink()            # the PC is reinstalled
    assert offsite_service.key_state(path) == "missing"

    restored = offsite_service.set_key_from_sheet(path, printed)
    assert restored == original
    assert offsite_service.encryption_key(path) == original


def test_a_backup_made_before_the_key_was_lost_opens_again_afterwards(shop):
    """The whole point of the sheet: the shop's books come back."""
    path = shop["app"].config["BACKUP_KEY_PATH"]
    printed = offsite_service.recovery_sheet_key(path)
    offsite_service.send_latest(**_paths(shop), now=NOW)

    (shop["tmp"] / "backup-encryption.key").unlink()            # everything on this PC is gone
    offsite_service.set_key_from_sheet(path, printed)           # only the paper survived

    name, sales = offsite_service.check(**_paths(shop), now=NOW)
    assert sales == 4                                          # the shop's sales, back


@pytest.mark.parametrize("typed,message", [
    ("", "Type the key"),
    ("not a key at all!", "doesn't look like"),
    ("c3VrYQ==", "32 bytes"),
])
def test_a_mistyped_recovery_key_says_what_is_wrong(shop, typed, message):
    with pytest.raises(ValueError, match=message):
        offsite_service.set_key_from_sheet(shop["app"].config["BACKUP_KEY_PATH"], typed)


def test_starting_a_new_key_is_deliberate_and_leaves_the_old_backups_locked(shop):
    path = shop["app"].config["BACKUP_KEY_PATH"]
    old = offsite_service.encryption_key(path)
    offsite_service.send_latest(**_paths(shop), now=NOW)

    new = offsite_service.start_new_key(path)
    assert new != old
    with pytest.raises(offsite.OffsiteError, match="could not be unlocked"):
        offsite_service.check(**_paths(shop), now=NOW)     # the old backup stays locked, loudly
