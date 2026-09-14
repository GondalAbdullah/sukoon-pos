"""The shop's clock (ADR-0024).

Timestamps are stored UTC. Anything a person reads — a screen, a receipt, the year
on an invoice number — is in the shop's timezone: the ``shop.timezone`` setting,
defaulting to Asia/Karachi. One fixed zone for the shop, never each PC's Windows
setting, so a mis-set machine cannot misprint receipts.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sukoon.services import settings_service

DEFAULT_TIMEZONE = "Asia/Karachi"
DISPLAY_FORMAT = "%Y-%m-%d %H:%M"

log = logging.getLogger(__name__)


def convert(dt: datetime, zone_name: str) -> datetime:
    """Pure: a stored timestamp in ``zone_name``. SQLite hands back naive values
    even for aware writes, so naive means UTC. An unknown zone falls back to the
    default rather than raising — a typo in a setting must not stop a sale."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Unknown shop.timezone %r; using %s", zone_name, DEFAULT_TIMEZONE)
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    return dt.astimezone(zone)


def shop_zone_name() -> str:
    return settings_service.get("shop.timezone") or DEFAULT_TIMEZONE


def to_shop_time(dt: datetime) -> datetime:
    return convert(dt, shop_zone_name())


def format_shop_time(dt: datetime | None, fmt: str = DISPLAY_FORMAT) -> str:
    return "—" if dt is None else to_shop_time(dt).strftime(fmt)
