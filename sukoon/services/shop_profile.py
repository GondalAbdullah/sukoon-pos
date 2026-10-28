"""The shop's own details — name, address, phone — as printed on receipts and statements.

No Flask import (ADR-0003 §1). The address and phone are entered under Settings → Shop details.
Before that screen existed a single free-text ``shop.contact`` setting was read (and never had a
screen of its own); it is still used as the address when no address has been entered.
"""
from __future__ import annotations

from dataclasses import dataclass

from sukoon.services import settings_service

NAME_KEY = "shop.name"
ADDRESS_KEY = "shop.address"
PHONE_KEY = "shop.phone"
_LEGACY_CONTACT_KEY = "shop.contact"
DEFAULT_NAME = "Al-Rehman General Store"
_MAX = {"name": 60, "address": 160, "phone": 40}


class ShopProfileError(ValueError):
    def __init__(self, message: str, *, field: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class ShopProfile:
    name: str
    address: str | None
    phone: str | None

    @property
    def contact_line(self) -> str | None:
        """Address and phone on one line, for a heading with room for only one."""
        parts = [p for p in (self.address, f"Ph: {self.phone}" if self.phone else None) if p]
        return " · ".join(parts) or None


def _clean(value: str | None) -> str | None:
    return " ".join((value or "").split()) or None


def get() -> ShopProfile:
    return ShopProfile(
        name=settings_service.get(NAME_KEY) or DEFAULT_NAME,
        address=_clean(settings_service.get(ADDRESS_KEY))
        or _clean(settings_service.get(_LEGACY_CONTACT_KEY)),
        phone=_clean(settings_service.get(PHONE_KEY)),
    )


def save(*, name: str | None, address: str | None, phone: str | None) -> ShopProfile:
    """Check everything first, then write; the caller commits."""
    values = {"name": _clean(name), "address": _clean(address), "phone": _clean(phone)}
    if not values["name"]:
        raise ShopProfileError("The shop needs a name.", field="name")
    for field, value in values.items():
        if value and len(value) > _MAX[field]:
            raise ShopProfileError(
                f"That {field} is too long ({_MAX[field]} characters at most).", field=field)
    settings_service.set(NAME_KEY, values["name"])
    settings_service.set(ADDRESS_KEY, values["address"] or "")
    settings_service.set(PHONE_KEY, values["phone"] or "")
    return get()
