"""Offsite backup as the shop uses it (ADR-0037): settings in, a copy out, and an honest status.

The transport lives in ``sukoon.offsite``. This assembles it from what the Admin typed, keeps the
two secrets where the WhatsApp key lives (encrypted by Windows, ADR-0033 §1), and records what
happened where an Admin can see it.

No Flask import (ADR-0003 §1) — callers pass the paths.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sukoon import backup, offsite
from sukoon.services import clock, settings_service
from sukoon.services.notifications import secret_store

ENABLED = "offsite.enabled"
ENDPOINT = "offsite.endpoint"
BUCKET = "offsite.bucket"
ACCESS_KEY_ID = "offsite.access_key_id"
PREFIX = "offsite.prefix"
STATUS_FILE = "offsite-status.json"
KEEP = 200                 # ~2 days at 15 minutes, plus the pre-upgrade copies
STALE_AFTER = timedelta(hours=2)
VERIFY_EVERY = timedelta(days=7)


class NotConfigured(RuntimeError):
    """Offsite backup hasn't been set up yet. Not an error — just nothing to do."""


class KeyUnreadable(RuntimeError):
    """The backup key is on this PC but this PC can't unlock it.

    What a reinstalled Windows looks like: the key was encrypted for a Windows account that no
    longer exists (uninstalling Sukoon removes that account). The backups themselves are fine —
    they need the key from the printed recovery sheet.
    """


@dataclass(frozen=True)
class OffsiteStatus:
    key: str                 # 'missing' | 'ready' | 'unreadable'
    configured: bool
    enabled: bool
    last_ok_at: datetime | None
    last_error: str | None
    last_object: str | None
    last_verified_at: datetime | None
    last_verified_sales: int | None

    @property
    def stale(self) -> bool:
        return self.enabled and (
            self.last_ok_at is None or datetime.now(UTC) - self.last_ok_at > STALE_AFTER)

    @property
    def last_ok_text(self) -> str:
        return clock.format_shop_time(self.last_ok_at) if self.last_ok_at else "never"

    @property
    def last_verified_text(self) -> str:
        return clock.format_shop_time(self.last_verified_at) if self.last_verified_at else "never"

    @property
    def verification_overdue(self) -> bool:
        if not self.enabled:
            return False
        return (self.last_verified_at is None
                or datetime.now(UTC) - self.last_verified_at > VERIFY_EVERY)


def is_enabled() -> bool:
    return settings_service.get(ENABLED) == "1"


def target(secret_path: str | Path) -> offsite.Target:
    """What the Admin typed, plus the secret only this PC can read."""
    endpoint = (settings_service.get(ENDPOINT) or "").strip()
    bucket = (settings_service.get(BUCKET) or "").strip()
    access_key_id = (settings_service.get(ACCESS_KEY_ID) or "").strip()
    try:
        secret = secret_store.load_key(secret_path)
    except secret_store.KeyStoreError as exc:
        # Same story as the backup key: a reinstalled Windows can no longer unlock what the old
        # account encrypted. This one is replaceable — it lives in the Cloudflare dashboard.
        raise KeyUnreadable(
            "The storage service's secret key saved on this computer can't be read — that happens "
            "when Windows or the Sukoon account has been reinstalled. Paste it again below; you "
            "can make a new one in your storage account if you no longer have it.") from exc
    if not (endpoint and bucket and access_key_id and secret):
        raise NotConfigured("Offsite backup is not set up yet.")
    return offsite.Target(endpoint=endpoint, bucket=bucket, access_key_id=access_key_id,
                          secret_access_key=secret,
                          prefix=(settings_service.get(PREFIX) or "sukoon").strip() or "sukoon")


def key_state(key_path: str | Path | None) -> str:
    """'missing', 'ready' or 'unreadable' — what the Settings screen needs to know."""
    if not key_path or not secret_store.has_key(key_path):
        return "missing"
    try:
        secret_store.load_key(key_path)
    except secret_store.KeyStoreError:
        return "unreadable"
    return "ready"


def encryption_key(key_path: str | Path, *, create: bool = False) -> bytes:
    """The key the backups are locked with. Created once, then never changed — every backup
    already offsite was locked with it (ADR-0037 §5)."""
    try:
        stored = secret_store.load_key(key_path)
    except secret_store.KeyStoreError as exc:
        # The file is there and this PC cannot unlock it. Never quietly make a new one: every
        # backup already offsite is locked with the old one, and a new key would strand them
        # silently. The way back is the recovery sheet.
        raise KeyUnreadable(
            "The backup key saved on this computer can't be read — that happens when Windows or "
            "the Sukoon account has been reinstalled. Enter the key from your printed recovery "
            "sheet to reach the backups already saved.") from exc
    if stored:
        return base64.b64decode(stored)
    if not create:
        raise NotConfigured("No backup key has been made yet.")
    key = offsite.new_key()
    secret_store.save_key(key_path, base64.b64encode(key).decode())
    return key


def set_key_from_sheet(key_path: str | Path, typed: str) -> bytes:
    """Take the key back from the printed recovery sheet (ADR-0037 §5).

    Without this the sheet is useless inside Sukoon: it existed, and nothing accepted it back.
    Spaces and line breaks are ignored, so it can be typed exactly as it is printed.
    """
    cleaned = "".join((typed or "").split())
    if not cleaned:
        raise ValueError("Type the key from the recovery sheet.")
    padding = "=" * (-len(cleaned) % 4)
    try:
        key = base64.b64decode(cleaned + padding, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("That doesn't look like a recovery key. Check for a mistyped character."
                         ) from exc
    if len(key) != offsite.KEY_BYTES:
        raise ValueError(f"A recovery key is {offsite.KEY_BYTES} bytes; that one is {len(key)}. "
                         f"Check the whole key was typed.")
    secret_store.save_key(key_path, base64.b64encode(key).decode())
    return key


def start_new_key(key_path: str | Path) -> bytes:
    """Deliberately replace the key. Everything already offsite stays locked with the old one."""
    secret_store.delete_key(key_path)
    return encryption_key(key_path, create=True)


def recovery_sheet_key(key_path: str | Path) -> str:
    """The key as it is printed: groups of four, so it can be typed back from paper."""
    raw = base64.b64encode(encryption_key(key_path)).decode().rstrip("=")
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def send_latest(*, backups_dir: str | Path, secret_path: str | Path, key_path: str | Path,
                now: datetime | None = None) -> str | None:
    """Put the newest local backup offsite. Returns its name, or None when there was nothing new."""
    now = now or datetime.now(UTC)
    backups_dir = Path(backups_dir)
    where = target(secret_path)
    key = encryption_key(key_path)
    local = sorted(backups_dir.glob("sukoon-*.db")) + sorted(backups_dir.glob("pre-upgrade-*.db"))
    if not local:
        return None
    newest = max(local, key=lambda path: path.stat().st_mtime)
    already = set(offsite.listing(where))
    if f"{newest.name}.enc" in already:
        return None
    name = offsite.upload(where, newest, key)
    offsite.prune(where, keep=KEEP)
    record(backups_dir, now, ok=True, object_name=name)
    return name


def check(*, backups_dir: str | Path, secret_path: str | Path, key_path: str | Path,
          now: datetime | None = None) -> tuple[str, int]:
    """Download the newest offsite backup, unlock it, open it (ADR-0037 §6)."""
    now = now or datetime.now(UTC)
    backups_dir = Path(backups_dir)
    scratch = backups_dir / "offsite-check.db"
    try:
        newest, sales = offsite.verify(target(secret_path), encryption_key(key_path), into=scratch)
    finally:
        scratch.unlink(missing_ok=True)
    record(backups_dir, now, ok=True, verified=(newest, sales))
    return newest, sales


def record(backups_dir: str | Path, now: datetime, *, ok: bool, error: str | None = None,
           object_name: str | None = None, verified: tuple[str, int] | None = None) -> None:
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    current = read_status_file(backups_dir)
    stamp = now.astimezone(UTC).isoformat()
    if ok:
        if object_name:
            current.update(last_ok_at=stamp, last_object=object_name, last_error=None)
        if verified:
            current.update(last_verified_at=stamp, last_verified_object=verified[0],
                           last_verified_sales=verified[1], last_error=None)
    else:
        current.update(last_failed_at=stamp, last_error=error)
    staging = backups_dir / (STATUS_FILE + ".tmp")
    staging.write_text(json.dumps(current), encoding="utf-8")
    os.replace(staging, backups_dir / STATUS_FILE)


def read_status_file(backups_dir: str | Path) -> dict:
    try:
        return json.loads((Path(backups_dir) / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _when(raw: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def describe(backups_dir: str | Path | None, secret_path: str | Path | None,
             key_path: str | Path | None = None) -> OffsiteStatus:
    if not backups_dir:
        return OffsiteStatus("missing", False, False, None, None, None, None, None)
    status = read_status_file(backups_dir)
    configured = bool((settings_service.get(ENDPOINT) or "").strip()
                      and (settings_service.get(BUCKET) or "").strip()
                      and secret_path and secret_store.has_key(secret_path))
    return OffsiteStatus(
        key=key_state(key_path),
        configured=configured, enabled=configured and is_enabled(),
        last_ok_at=_when(status.get("last_ok_at")), last_error=status.get("last_error"),
        last_object=status.get("last_object"),
        last_verified_at=_when(status.get("last_verified_at")),
        last_verified_sales=status.get("last_verified_sales"))


__all__ = ["KeyUnreadable", "NotConfigured", "OffsiteStatus", "backup", "check", "describe",
           "encryption_key", "is_enabled", "key_state", "record", "recovery_sheet_key",
           "send_latest", "set_key_from_sheet", "start_new_key", "target"]
