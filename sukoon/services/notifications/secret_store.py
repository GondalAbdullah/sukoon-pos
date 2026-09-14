"""Where the WhatsApp access key lives (ADR-0033 §1). No Flask, no database.

On Windows the key is encrypted with DPAPI (via ctypes — no pywin32), so the file is
useless copied to another PC or account, and database backups never contain it. On
other systems (the Linux development machine) a file readable only by its owner stands
in. The key is never logged, never rendered, never returned to a screen.

Honest limit: the DPAPI branch can only be exercised on Windows; it is tested there in
Phase 7 (context.md §4). Which Windows account it binds to is the Phase 7 grill's call.
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_MAGIC = "sukoon-whatsapp-key-v1"
_ENTROPY = b"sukoon-whatsapp-access-key"


class KeyStoreError(Exception):
    pass


def _is_windows() -> bool:
    return sys.platform == "win32"


# --- DPAPI (Windows) ---------------------------------------------------------------------

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, *, protect: bool) -> bytes:  # pragma: no cover — Windows only
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    out = _Blob()
    entropy = _blob(_ENTROPY)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(_blob(data)), None, ctypes.byref(entropy), None, None,
            0x1,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(out))
    if not ok:
        raise KeyStoreError("Windows could not protect or unprotect the WhatsApp key.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


# --- the store ------------------------------------------------------------------------------

def save_key(path: str | Path, key: str) -> None:
    key = (key or "").strip()
    if not key:
        raise KeyStoreError("Paste the access key first.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_windows():  # pragma: no cover — Windows only
        body = "dpapi\n" + base64.b64encode(_dpapi(key.encode(), protect=True)).decode()
    else:
        body = "plain\n" + base64.b64encode(key.encode()).decode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(f"{_MAGIC}\n{body}\n")
    os.replace(tmp, path)
    if not _is_windows():
        os.chmod(path, 0o600)


def load_key(path: str | Path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        magic, kind, blob = path.read_text(encoding="ascii").strip().split("\n")
        if magic != _MAGIC:
            raise ValueError
        raw = base64.b64decode(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise KeyStoreError("The saved WhatsApp key file is damaged. Replace the key.") from exc
    if kind == "dpapi":
        if not _is_windows():
            raise KeyStoreError("This key was saved on Windows and can only be read there.")
        return _dpapi(raw, protect=False).decode()  # pragma: no cover — Windows only
    return raw.decode()


def has_key(path: str | Path) -> bool:
    return Path(path).is_file()


def saved_at(path: str | Path) -> datetime | None:
    path = Path(path)
    return datetime.fromtimestamp(path.stat().st_mtime, UTC) if path.is_file() else None


def delete_key(path: str | Path) -> None:
    Path(path).unlink(missing_ok=True)
