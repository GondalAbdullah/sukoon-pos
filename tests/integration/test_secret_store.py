"""The WhatsApp access key store (ADR-0033 §1). The DPAPI branch only runs on Windows and
is tested there in Phase 7; here, the non-Windows stand-in and the guarantees around it."""
from __future__ import annotations

import stat
import sys

import pytest

from sukoon.extensions import db
from sukoon.services.notifications import secret_store

KEY = "EAAG-super-secret-key-123"


def test_roundtrip_and_owner_only_permissions(tmp_path):
    path = tmp_path / "instance" / "whatsapp.key"
    assert not secret_store.has_key(path) and secret_store.load_key(path) is None
    secret_store.save_key(path, f"  {KEY}\n")
    assert secret_store.load_key(path) == KEY and secret_store.saved_at(path) is not None
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # base64 only stops a glance at the file — it is NOT protection. Off Windows the
    # protection is the owner-only permission above; on Windows it is DPAPI.
    # bytes, not text: on Windows this file is DPAPI ciphertext, and decoding it with
    # whatever code page the machine happens to use is meaningless (and can throw).
    assert KEY.encode() not in path.read_bytes()
    secret_store.delete_key(path)
    assert not secret_store.has_key(path)


def test_an_empty_key_is_refused(tmp_path):
    with pytest.raises(secret_store.KeyStoreError):
        secret_store.save_key(tmp_path / "k", "   ")


def test_a_damaged_file_is_explained(tmp_path):
    path = tmp_path / "k"
    path.write_text("not a key file", encoding="utf-8")
    with pytest.raises(secret_store.KeyStoreError, match="damaged"):
        secret_store.load_key(path)


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows refusal")
def test_a_windows_protected_key_is_not_read_elsewhere(tmp_path):
    path = tmp_path / "k"
    path.write_text("sukoon-whatsapp-key-v1\ndpapi\nAAAA\n", encoding="utf-8")
    with pytest.raises(secret_store.KeyStoreError, match="saved on Windows"):
        secret_store.load_key(path)


def test_the_key_never_reaches_the_database(app, tmp_path):
    secret_store.save_key(tmp_path / "k", KEY)
    dump = "\n".join(db.session.connection().connection.driver_connection.iterdump())
    assert KEY not in dump


def test_the_factory_builds_meta_with_the_stored_key_and_number_id(app, tmp_path):
    from sukoon.services import settings_service
    from sukoon.services.notifications.providers.factory import PHONE_NUMBER_ID, build_provider
    from sukoon.services.notifications.providers.meta import MetaProvider

    path = tmp_path / "k"
    secret_store.save_key(path, KEY)
    settings_service.set(PHONE_NUMBER_ID, " 1234567890 ")
    db.session.commit()
    p = build_provider(kind="meta", key_path=str(path), api_version="v99.0")
    assert isinstance(p, MetaProvider)
    assert (p.access_key, p.phone_number_id, p.api_version) == (KEY, "1234567890", "v99.0")
    assert build_provider(kind="fake", key_path=str(path)).name == "fake"


def test_a_damaged_key_file_becomes_a_clear_no_key_pause_not_a_crash(app, tmp_path):
    from sukoon.services.notifications.policy import Outcome
    from sukoon.services.notifications.providers.factory import build_provider

    path = tmp_path / "k"
    path.write_text("garbage", encoding="utf-8")
    r = build_provider(kind="meta", key_path=str(path)).check()
    assert (r.outcome, r.error) == (Outcome.ACCOUNT_BROKEN, "No WhatsApp access key is set")
