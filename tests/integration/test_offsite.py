"""Offsite backup (ADR-0037): encryption, signing, and the check that a backup can actually
come back.

The signature is cross-checked against a second implementation written here straight from the
AWS SigV4 specification — if both agree, the shape is right; the final arbiter is the real
storage service, which either accepts a request or refuses it.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon import offsite

SECRET = "r2-secret-for-tests-only"
KEY_ID = "r2-access-key-id"


# --- encryption --------------------------------------------------------------------------------

def test_a_backup_is_unreadable_without_the_key_and_exact_again_with_it():
    key = offsite.new_key()
    database = b"SQLite format 3\x00" + b"Haji Usman owes Rs 10,030" + bytes(500)
    blob = offsite.encrypt(database, key)

    assert b"Haji Usman" not in blob                      # the provider holds bytes it can't read
    assert blob.startswith(offsite.MAGIC)
    assert offsite.decrypt(blob, key) == database


def test_the_wrong_key_is_refused_rather_than_producing_rubbish():
    blob = offsite.encrypt(b"the shop's books", offsite.new_key())
    with pytest.raises(offsite.OffsiteError, match="not the one it was encrypted with"):
        offsite.decrypt(blob, offsite.new_key())


def test_a_tampered_backup_is_refused(monkeypatch):
    key = offsite.new_key()
    blob = bytearray(offsite.encrypt(b"the shop's books", key))
    blob[-5] ^= 0x01                                       # one bit, somewhere in the ciphertext
    with pytest.raises(offsite.OffsiteError, match="damaged or altered"):
        offsite.decrypt(bytes(blob), key)


def test_something_that_is_not_a_sukoon_backup_is_refused():
    with pytest.raises(offsite.OffsiteError, match="not a Sukoon backup"):
        offsite.decrypt(b"just some file", offsite.new_key())


# --- signing -----------------------------------------------------------------------------------

def _independent_signature(method, path, query, payload, amz_date, region="auto"):
    """Written from the SigV4 specification, deliberately not sharing code with offsite.py."""
    datestamp = amz_date[:8]
    payload_hash = hashlib.sha256(payload).hexdigest()
    canonical = "\n".join([
        method, path, query,
        f"host:storage.example\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n",
        "host;x-amz-content-sha256;x-amz-date", payload_hash])
    scope = f"{datestamp}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    key = f"AWS4{SECRET}".encode()
    for part in (datestamp, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


def test_the_request_is_signed_the_way_the_specification_says(monkeypatch):
    captured = {}

    class FakeResponse:
        def read(self):
            return b"<ListBucketResult></ListBucketResult>"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(offsite.urllib.request, "urlopen", fake_urlopen)
    target = offsite.Target(endpoint="https://storage.example", bucket="sukoon-books",
                            access_key_id=KEY_ID, secret_access_key=SECRET)
    now = datetime(2026, 9, 18, 9, 30, tzinfo=UTC)
    offsite._request(target, "PUT", "sukoon/backup.db.enc", body=b"ciphertext", now=now)

    expected = _independent_signature("PUT", "/sukoon-books/sukoon/backup.db.enc", "",
                                      b"ciphertext", "20260918T093000Z")
    authorization = captured["headers"]["Authorization"]
    assert f"Signature={expected}" in authorization
    assert f"Credential={KEY_ID}/20260918/auto/s3/aws4_request" in authorization
    assert SECRET not in authorization and SECRET not in captured["url"]


# --- a stand-in storage service -----------------------------------------------------------------

class _FakeS3(BaseHTTPRequestHandler):
    store: dict[str, bytes] = {}

    def _name(self):
        return self.path.split("?", 1)[0].split("/sukoon-books/", 1)[-1]

    def do_PUT(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if "Authorization" not in self.headers:
            self.send_response(403)
            self.end_headers()
            return
        type(self).store[self._name()] = body
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if "list-type=2" in self.path:
            xml = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in sorted(self.store))
            payload = f"<ListBucketResult>{xml}</ListBucketResult>".encode()
        else:
            payload = self.store.get(self._name())
            if payload is None:
                self.send_response(404)
                self.end_headers()
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_DELETE(self):  # noqa: N802
        type(self).store.pop(self._name(), None)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def storage():
    _FakeS3.store = {}
    httpd = HTTPServer(("127.0.0.1", 0), _FakeS3)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield offsite.Target(endpoint=f"http://127.0.0.1:{httpd.server_address[1]}",
                         bucket="sukoon-books", access_key_id=KEY_ID, secret_access_key=SECRET)
    httpd.shutdown()


def _shop_database(path, sales: int):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sale (id INTEGER PRIMARY KEY, total INTEGER)")
    connection.executemany("INSERT INTO sale (total) VALUES (?)", [(i,) for i in range(sales)])
    connection.commit()
    connection.close()
    return path


def test_a_backup_goes_up_encrypted_and_comes_back_as_a_working_database(storage, tmp_path):
    key = offsite.new_key()
    local = _shop_database(tmp_path / "sukoon-20260918-090000.db", sales=7)

    name = offsite.upload(storage, local, key)
    assert name == "sukoon-20260918-090000.db.enc"
    assert offsite.listing(storage) == [name]
    assert b"SQLite format 3" not in _FakeS3.store[f"sukoon/{name}"]   # stored encrypted

    newest, sales = offsite.verify(storage, key, into=tmp_path / "check.db")
    assert newest == name and sales == 7


def test_verifying_with_the_wrong_key_fails_loudly(storage, tmp_path):
    offsite.upload(storage, _shop_database(tmp_path / "sukoon-20260918-090000.db", 3),
                   offsite.new_key())
    with pytest.raises(offsite.OffsiteError, match="could not be unlocked"):
        offsite.verify(storage, offsite.new_key(), into=tmp_path / "check.db")


def test_verifying_an_empty_bucket_says_so(storage, tmp_path):
    with pytest.raises(offsite.OffsiteError, match="no backups in the offsite storage"):
        offsite.verify(storage, offsite.new_key(), into=tmp_path / "check.db")


def test_retention_keeps_the_newest_and_removes_the_rest(storage, tmp_path):
    key = offsite.new_key()
    for hour in range(6):
        local = _shop_database(tmp_path / f"sukoon-20260918-0{hour}0000.db", sales=hour)
        offsite.upload(storage, local, key)
    removed = offsite.prune(storage, keep=3)
    assert len(removed) == 3
    assert offsite.listing(storage) == ["sukoon-20260918-030000.db.enc",
                                        "sukoon-20260918-040000.db.enc",
                                        "sukoon-20260918-050000.db.enc"]


def test_a_refusal_from_the_storage_service_is_explained_not_swallowed(storage, tmp_path):
    broken = offsite.Target(endpoint=storage.endpoint, bucket="sukoon-books",
                            access_key_id=KEY_ID, secret_access_key=SECRET, prefix="sukoon")
    with pytest.raises(offsite.OffsiteError, match="refused the request|could not be reached"):
        offsite.fetch(broken, "nothing-here.enc")
