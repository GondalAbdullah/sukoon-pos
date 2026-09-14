"""Choose the provider from configuration (no Flask import; callers pass config)."""
from __future__ import annotations

from sukoon.services import settings_service
from sukoon.services.notifications import secret_store
from sukoon.services.notifications.providers.base import FakeProvider, Provider
from sukoon.services.notifications.providers.meta import DEFAULT_API_VERSION, MetaProvider

PHONE_NUMBER_ID = "whatsapp.phone_number_id"
_fake_singleton = FakeProvider()


def build_provider(*, kind: str, key_path: str, api_version: str | None = None) -> Provider:
    if kind == "fake":
        return _fake_singleton
    try:
        key = secret_store.load_key(key_path)
    except secret_store.KeyStoreError:
        key = None  # surfaces as "account broken: no key" -> a clear Admin banner
    number_id = (settings_service.get(PHONE_NUMBER_ID) or "").strip() or None
    return MetaProvider(access_key=key, phone_number_id=number_id,
                        api_version=api_version or DEFAULT_API_VERSION)
