"""What an Admin is told about the shop's backups (ADR-0037 §6).

A backup nobody looks at is a belief, not a backup — so the Settings screen says when the last one
worked, how old it is, and says so loudly when it has gone stale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sukoon import backup
from sukoon.services import clock

STALE_AFTER = timedelta(hours=2)   # four missed runs of a fifteen-minute backup


@dataclass(frozen=True)
class BackupState:
    configured: bool
    last_ok_at: datetime | None
    last_error: str | None
    count: int
    folder: str | None

    @property
    def stale(self) -> bool:
        return self.configured and (
            self.last_ok_at is None or datetime.now(UTC) - self.last_ok_at > STALE_AFTER)

    @property
    def last_ok_text(self) -> str:
        if self.last_ok_at is None:
            return "never"
        return clock.format_shop_time(self.last_ok_at)


def describe(backups_dir: str | Path | None) -> BackupState:
    if not backups_dir:
        # Development: backups run only for an installed copy (startup.build_app).
        return BackupState(configured=False, last_ok_at=None, last_error=None, count=0, folder=None)
    folder = Path(backups_dir)
    status = backup.read_status(folder)
    raw = status.get("last_ok_at")
    try:
        last_ok = datetime.fromisoformat(raw) if raw else None
    except ValueError:
        last_ok = None
    return BackupState(
        configured=True, last_ok_at=last_ok, last_error=status.get("last_error"),
        count=len(list(folder.glob("sukoon-*.db"))), folder=str(folder))
