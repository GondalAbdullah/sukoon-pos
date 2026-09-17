"""Local database backups (ADR-0037 §2–3, ADR-0038 §11).

Two kinds, one mechanism:

* **Scheduled** — every 15 minutes the background jobs take a snapshot, and keep it only if
  the shop's data changed since the last one. The last 24 hours are kept at that
  granularity, then the newest of each of 14 days.
* **Pre-upgrade** — taken before any migration, and never deleted by retention: they are the
  way back if an upgrade goes wrong.

A snapshot uses **SQLite's online backup API**, never a file copy: Sukoon runs in WAL mode, so
recent sales can sit in ``sukoon.db-wal`` rather than the main file, and a copy of the main file
alone silently loses them (the tests prove this). Every snapshot passes ``integrity_check``
before it counts.

Until the offsite account exists (O-26, O-27) these copies live on the shop PC only, so they
guard against mistakes and bad upgrades — not against losing the PC.

Status goes to ``backups/status.json``, **not the database**: writing "backup succeeded" into
the database would change it, and every snapshot would then differ from the last.

Pure stdlib; no Flask (ADR-0003 §1).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEDULED_RE = re.compile(r"^sukoon-(\d{8}-\d{6})\.db$")
PRE_UPGRADE_PREFIX = "pre-upgrade-"
STATUS_FILE = "status.json"
STAMP = "%Y%m%d-%H%M%S"
KEEP_RECENT = timedelta(hours=24)
KEEP_DAILY = 14


class BackupError(RuntimeError):
    """A snapshot or restore could not be completed. The message says what failed."""


@dataclass(frozen=True)
class ScheduledResult:
    path: Path | None       # the new backup, or None when nothing had changed
    unchanged: bool
    removed: tuple[Path, ...] = ()


def snapshot(db_path: str | Path, dest: str | Path) -> Path:
    """A consistent copy of the database, safe to take while the shop is selling."""
    db_path, dest = Path(db_path), Path(dest)
    if not db_path.is_file():
        raise BackupError(f"There is no database at {db_path} to back up.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    try:
        source = sqlite3.connect(db_path)
        try:
            target = sqlite3.connect(partial)
            try:
                source.backup(target)
                verdict = target.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                target.close()
        finally:
            source.close()
    except sqlite3.Error as exc:
        partial.unlink(missing_ok=True)
        raise BackupError(f"The backup of {db_path} failed: {exc}") from exc
    if verdict != "ok":
        partial.unlink(missing_ok=True)
        raise BackupError(f"The backup of {db_path} failed its integrity check: {verdict}")
    os.replace(partial, dest)
    return dest


def restore(backup: str | Path, db_path: str | Path) -> None:
    """Put a backup back in place of the database.

    Every connection to ``db_path`` must be closed first. Its ``-wal`` and ``-shm`` files are
    removed: they belong to the state being thrown away, and SQLite would otherwise replay the
    discarded changes on top of the restored file.
    """
    backup, db_path = Path(backup), Path(db_path)
    if not backup.is_file():
        raise BackupError(f"The backup {backup} doesn't exist.")
    staging = db_path.with_name(db_path.name + ".restoring")
    shutil.copyfile(backup, staging)
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    os.replace(staging, db_path)


def scheduled_name(now: datetime) -> str:
    return f"sukoon-{now.astimezone(UTC):{STAMP}}.db"


def pre_upgrade_name(now: datetime, from_revision: str | None, to_revision: str) -> str:
    return (f"{PRE_UPGRADE_PREFIX}{now.astimezone(UTC):{STAMP}}"
            f"-{from_revision or 'empty'}-to-{to_revision}.db")


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _scheduled(backups_dir: Path) -> list[tuple[datetime, Path]]:
    found = []
    for path in backups_dir.glob("sukoon-*.db"):
        match = SCHEDULED_RE.match(path.name)
        if match:
            found.append((datetime.strptime(match.group(1), STAMP).replace(tzinfo=UTC), path))
    return sorted(found)


def prune(backups_dir: str | Path, now: datetime) -> tuple[Path, ...]:
    """Keep everything from the last 24 hours, then the newest backup of each of the 14 most
    recent days before that. Pre-upgrade backups are never touched."""
    backups = _scheduled(Path(backups_dir))
    recent_cutoff = now - KEEP_RECENT
    newest_per_day: dict = {}
    for stamp, path in backups:
        if stamp < recent_cutoff:
            newest_per_day[stamp.date()] = path  # sorted ascending, so the last one wins
    keep_days = set(sorted(newest_per_day)[-KEEP_DAILY:])
    keep = {newest_per_day[d] for d in keep_days}
    removed = []
    for stamp, path in backups:
        if stamp >= recent_cutoff or path in keep:
            continue
        path.unlink(missing_ok=True)
        removed.append(path)
    return tuple(removed)


def run_scheduled(db_path: str | Path, backups_dir: str | Path, now: datetime) -> ScheduledResult:
    """Take a snapshot; keep it only if the data changed; apply retention."""
    backups_dir = Path(backups_dir)
    candidate = snapshot(db_path, backups_dir / (scheduled_name(now) + ".candidate"))
    previous = _scheduled(backups_dir)
    if previous and _digest(previous[-1][1]) == _digest(candidate):
        candidate.unlink()
        return ScheduledResult(path=None, unchanged=True, removed=prune(backups_dir, now))
    final = backups_dir / scheduled_name(now)
    os.replace(candidate, final)
    return ScheduledResult(path=final, unchanged=False, removed=prune(backups_dir, now))


def record_status(backups_dir: str | Path, now: datetime, *, ok: bool,
                  error: str | None = None) -> None:
    """What an Admin sees: when the last backup succeeded, and the last failure if any."""
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    current = read_status(backups_dir)
    if ok:
        current.update(last_ok_at=now.astimezone(UTC).isoformat(), last_error=None)
    else:
        current.update(last_failed_at=now.astimezone(UTC).isoformat(), last_error=error)
    staging = backups_dir / (STATUS_FILE + ".tmp")
    staging.write_text(json.dumps(current), encoding="utf-8")
    os.replace(staging, backups_dir / STATUS_FILE)


def read_status(backups_dir: str | Path) -> dict:
    try:
        return json.loads((Path(backups_dir) / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
