"""Offsite backup: the shop's database, encrypted here, kept somewhere that isn't the shop
(ADR-0037 §1, §4, §5).

The local backups protect against mistakes and bad upgrades. These protect against losing the PC
itself — theft, fire, a dead disk.

Two things make it safe to put a shop's books on someone else's computer:

* **Encrypted before it leaves.** AES-256-GCM, with a key generated on the shop PC and printed on
  a recovery sheet (ADR-0037 §5). The storage provider holds bytes it cannot read. GCM also
  *authenticates*: a tampered or truncated object fails to decrypt rather than restoring quietly
  wrong data.
* **Checked, not assumed.** ``verify(...)`` downloads the newest object, decrypts it, opens it as a
  database and reads the latest sale out of it — the weekly proof ADR-0037 §6 requires.

Talks S3 over the standard library (SigV4 signing with ``hmac``, requests with ``urllib``), the
same reasoning as the WhatsApp adapter in ADR-0027: no extra HTTP dependency to bundle. Works with
Cloudflare R2, Backblaze B2 and anything else speaking S3.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"SUKOON-BACKUP-1\n"
NONCE_BYTES = 12
KEY_BYTES = 32
_ALGORITHM = "AWS4-HMAC-SHA256"
_SERVICE = "s3"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class OffsiteError(RuntimeError):
    """Anything that stopped a backup reaching, or coming back from, offsite storage."""


@dataclass(frozen=True)
class Target:
    """Where backups go. The secret never leaves this object."""

    endpoint: str            # https://<account>.r2.cloudflarestorage.com
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = "auto"     # R2 uses "auto"
    prefix: str = "sukoon"

    @property
    def host(self) -> str:
        return urlsplit(self.endpoint).netloc


# --- encryption -------------------------------------------------------------------------------

def new_key() -> bytes:
    import secrets

    return secrets.token_bytes(KEY_BYTES)


def encrypt(data: bytes, key: bytes) -> bytes:
    import secrets

    if len(key) != KEY_BYTES:
        raise OffsiteError("The backup key is the wrong length.")
    nonce = secrets.token_bytes(NONCE_BYTES)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def decrypt(blob: bytes, key: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise OffsiteError("That file is not a Sukoon backup.")
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE_BYTES]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE_BYTES:], MAGIC)
    except InvalidTag as exc:
        raise OffsiteError(
            "This backup could not be unlocked: either the recovery key is not the one it was "
            "encrypted with, or the file has been damaged or altered.") from exc


# --- S3, signed by hand -------------------------------------------------------------------------

def _signing_key(secret: str, datestamp: str, region: str) -> bytes:
    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode(), hashlib.sha256).digest()

    return sign(sign(sign(sign(f"AWS4{secret}".encode(), datestamp), region), _SERVICE),
                "aws4_request")


def _request(target: Target, method: str, key_name: str = "", *, query: str = "",
             body: bytes = b"", now: datetime | None = None, timeout: float = 60.0) -> bytes:
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest() if body else _EMPTY_SHA256

    path = f"/{target.bucket}"
    if key_name:
        path += "/" + quote(key_name, safe="/")
    canonical_headers = (f"host:{target.host}\n"
                         f"x-amz-content-sha256:{payload_hash}\n"
                         f"x-amz-date:{amz_date}\n")
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([method, path, query, canonical_headers, signed_headers,
                                   payload_hash])
    scope = f"{datestamp}/{target.region}/{_SERVICE}/aws4_request"
    to_sign = "\n".join([_ALGORITHM, amz_date, scope,
                         hashlib.sha256(canonical_request.encode()).hexdigest()])
    signature = hmac.new(_signing_key(target.secret_access_key, datestamp, target.region),
                         to_sign.encode(), hashlib.sha256).hexdigest()

    url = f"{target.endpoint.rstrip('/')}{path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(url, data=body or None, method=method)
    request.add_header("Host", target.host)
    request.add_header("x-amz-date", amz_date)
    request.add_header("x-amz-content-sha256", payload_hash)
    request.add_header("Authorization",
                       f"{_ALGORITHM} Credential={target.access_key_id}/{scope}, "
                       f"SignedHeaders={signed_headers}, Signature={signature}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode("utf-8", "replace")
        raise OffsiteError(
            f"The storage service refused the request ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise OffsiteError(f"The storage service could not be reached: {exc}") from exc


def put(target: Target, name: str, body: bytes) -> None:
    _request(target, "PUT", f"{target.prefix}/{name}", body=body)


def fetch(target: Target, name: str) -> bytes:
    return _request(target, "GET", f"{target.prefix}/{name}")


def delete(target: Target, name: str) -> None:
    _request(target, "DELETE", f"{target.prefix}/{name}")


def listing(target: Target) -> list[str]:
    """Every backup already offsite, oldest first. Names only — that is all retention needs."""
    query = f"list-type=2&prefix={quote(target.prefix + '/', safe='')}"
    root = ET.fromstring(_request(target, "GET", query=query))
    # S3 replies are namespaced, and providers differ on the namespace: match on the tag name.
    keys = [(element.text or "") for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "Key"]
    return sorted(key.split("/", 1)[1] for key in keys if "/" in key)


# --- what the shop actually does ------------------------------------------------------------

def upload(target: Target, backup_path: str | Path, key: bytes, *, name: str | None = None) -> str:
    path = Path(backup_path)
    blob = encrypt(path.read_bytes(), key)
    object_name = name or f"{path.name}.enc"
    put(target, object_name, blob)
    return object_name


def verify(target: Target, key: bytes, *, into: str | Path) -> tuple[str, int]:
    """Download the newest backup, unlock it, open it, and count its sales.

    This is the weekly proof (ADR-0037 §6): a backup that cannot be decrypted and opened is not a
    backup, and the shop should learn that on a quiet Tuesday.
    """
    names = listing(target)
    if not names:
        raise OffsiteError("There are no backups in the offsite storage yet.")
    newest = names[-1]
    restored = Path(into)
    restored.write_bytes(decrypt(fetch(target, newest), key))
    connection = sqlite3.connect(restored)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise OffsiteError(f"The offsite backup {newest} is damaged.")
        sales = connection.execute("SELECT count(*) FROM sale").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise OffsiteError(
            f"The offsite backup {newest} did not open as a database: {exc}") from exc
    finally:
        connection.close()
    return newest, sales


def prune(target: Target, keep: int) -> list[str]:
    """Keep the newest ``keep`` objects. Names sort by timestamp, as the local backups do."""
    names = listing(target)
    removed = []
    for name in names[:-keep] if keep < len(names) else []:
        delete(target, name)
        removed.append(name)
    return removed
