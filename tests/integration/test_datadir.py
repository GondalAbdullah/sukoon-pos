"""Where an installed Sukoon keeps the shop's data, and the session key it generates
(ADR-0036, ADR-0038 §7)."""
from __future__ import annotations

import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from sukoon import config, datadir


def test_an_explicit_folder_wins_everywhere(tmp_path):
    env = {"SUKOON_DATA_DIR": str(tmp_path / "drill"), "ProgramData": r"C:\ProgramData"}
    assert datadir.resolve(env, "win32") == tmp_path / "drill"
    assert datadir.resolve(env, "linux") == tmp_path / "drill"


def test_windows_defaults_to_programdata_and_nowhere_else_has_a_default():
    assert datadir.resolve({"ProgramData": r"D:\ProgramData"}, "win32") == \
        Path(r"D:\ProgramData") / "Sukoon"
    assert datadir.resolve({}, "win32") == Path(r"C:\ProgramData") / "Sukoon"  # ADR-0036
    assert datadir.resolve({}, "linux") is None  # development keeps instance/


def test_prepare_creates_the_layout_under_one_folder(tmp_path):
    layout = datadir.prepare(tmp_path / "Sukoon")
    for folder in (layout.root, layout.logs, layout.backups):
        assert folder.is_dir()
    for path in (layout.database, layout.whatsapp_key, layout.worker_lock,
                 layout.secret_key_file):
        assert path.parent == layout.root
    assert not list(layout.root.glob(".write-check-*"))  # the probe cleans up after itself


def test_an_unwritable_data_folder_stops_start_up_with_a_message_naming_it(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    with pytest.raises(datadir.DataFolderError) as err:
        datadir.prepare(blocker / "Sukoon")  # portable: can't create a folder inside a file
    message = str(err.value)
    assert str(blocker / "Sukoon") in message and "won't start" in message


def test_the_session_key_is_made_once_and_then_kept(tmp_path):
    path = tmp_path / "secret.key"
    first = datadir.load_or_create_secret_key(path)
    assert len(first) == 64 and datadir.load_or_create_secret_key(path) == first
    if sys.platform != "win32":  # on Windows the data folder's ACL is the protection
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_two_installs_never_share_a_session_key(tmp_path):
    a = datadir.load_or_create_secret_key(tmp_path / "a.key")
    b = datadir.load_or_create_secret_key(tmp_path / "b.key")
    assert a != b


def test_a_key_file_still_being_written_is_waited_for_not_called_empty(tmp_path, monkeypatch):
    """The race the O_EXCL create leaves open: one process has created the file and not yet
    written it when a second reads it. The second must wait for the key."""
    path = tmp_path / "secret.key"
    path.touch()  # the other process's half-finished create
    monkeypatch.setattr(datadir, "_EMPTY_KEY_WAIT_SECONDS", 0.05)

    def finish_writing():
        time.sleep(0.15)
        path.write_text("k" * 64, encoding="ascii")

    writer = threading.Thread(target=finish_writing)
    writer.start()
    try:
        assert datadir.load_or_create_secret_key(path) == "k" * 64
    finally:
        writer.join()


def test_a_key_file_that_stays_empty_is_explained(tmp_path, monkeypatch):
    path = tmp_path / "secret.key"
    path.touch()
    monkeypatch.setattr(datadir, "_EMPTY_KEY_RETRIES", 2)
    monkeypatch.setattr(datadir, "_EMPTY_KEY_WAIT_SECONDS", 0)
    with pytest.raises(datadir.DataFolderError, match="empty"):
        datadir.load_or_create_secret_key(path)


def test_building_a_database_address_creates_nothing(tmp_path):
    """It used to makedirs at import time, against the current directory — which would crash
    an installed copy started by Windows from System32 before it knew its data folder."""
    missing = tmp_path / "nowhere" / "sukoon.db"
    assert config._sqlite_uri(str(missing)) == f"sqlite:///{missing}"
    assert not missing.parent.exists()


def test_a_relative_database_path_means_the_project_root_as_documented(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # launched from somewhere else entirely
    assert config._sqlite_uri("instance/sukoon.db") == \
        f"sqlite:///{config.PROJECT_ROOT / 'instance' / 'sukoon.db'}"
