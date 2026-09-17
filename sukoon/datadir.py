"""Where an installed Sukoon keeps the shop's data (ADR-0036).

An installed copy keeps everything that belongs to the shop — the database, logs, local
backups, the WhatsApp key and the generated ``SECRET_KEY`` — under one fixed folder,
``C:\\ProgramData\\Sukoon\\``. Nothing of the shop's lives beside the program, so an upgrade
can't overwrite it and an uninstall doesn't take it.

This module only works out paths and prepares the folder. It is called by the launcher
(``sukoon.startup``), never by ``create_app``, so tests and ``flask`` commands never touch a
real data folder by accident.
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "SUKOON_DATA_DIR"
_EMPTY_KEY_RETRIES = 20
_EMPTY_KEY_WAIT_SECONDS = 0.1


class DataFolderError(RuntimeError):
    """The data folder can't be created or written. Raised at start-up, with a message a
    person can act on, instead of failing later at the first sale (ADR-0036 consequences)."""


@dataclass(frozen=True)
class DataLayout:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "sukoon.db"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def whatsapp_key(self) -> Path:
        return self.root / "whatsapp.key"

    @property
    def worker_lock(self) -> Path:
        return self.root / "sukoon-worker.lock"

    @property
    def secret_key_file(self) -> Path:
        return self.root / "secret.key"


def resolve(environ: Mapping[str, str] = os.environ, platform: str = sys.platform) -> Path | None:
    """The data folder for this machine, or ``None`` when there isn't one.

    ``SUKOON_DATA_DIR`` wins, so the folder can be pointed elsewhere for a drill or a test.
    On Windows the default is ``%ProgramData%\\Sukoon`` — ADR-0036 fixes it there. Off Windows
    there is no installed layout, so development keeps using the project's ``instance/``.
    """
    explicit = environ.get(DATA_DIR_ENV)
    if explicit:
        return Path(explicit)
    if platform == "win32":
        return Path(environ.get("ProgramData") or r"C:\ProgramData") / "Sukoon"
    return None


def prepare(root: Path) -> DataLayout:
    """Create the folder and prove it's writable, or raise ``DataFolderError`` naming it."""
    layout = DataLayout(Path(root))
    try:
        for folder in (layout.root, layout.logs, layout.backups):
            folder.mkdir(parents=True, exist_ok=True)
        probe = layout.root / f".write-check-{os.getpid()}"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise DataFolderError(
            f"Sukoon can't write to its data folder, {layout.root}. The shop's database lives "
            f"there, so Sukoon won't start without it. Check the folder exists and that the "
            f"Sukoon account is allowed to change it. ({exc.strerror or exc})"
        ) from exc
    return layout


def load_or_create_secret_key(path: Path) -> str:
    """The key that signs sessions, generated on first start and kept in the data folder —
    never shipped in the installer, never in the database (ADR-0038 §7).

    Created with ``O_EXCL``, so two processes starting at the same moment can't each write a
    different key and sign each other's sessions out. The loser of that race can find the file
    created but not yet written, so it waits briefly for the key rather than calling an
    in-progress file "empty".
    """
    path = Path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        for _ in range(_EMPTY_KEY_RETRIES):
            key = path.read_text(encoding="ascii").strip()
            if key:
                return key
            time.sleep(_EMPTY_KEY_WAIT_SECONDS)
        raise DataFolderError(
            f"The session key file {path} is empty. Delete it and restart Sukoon; everyone "
            f"will need to sign in again."
        ) from None
    key = secrets.token_hex(32)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key)
    return key
