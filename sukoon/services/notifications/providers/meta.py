"""Meta WhatsApp Business Cloud API adapter (ADR-0027). Standard library only.

Classifies every response into ADR-0029's five outcomes. **The error-code mapping below
is from Meta's documentation as remembered when this was written, NOT verified against
a current source** — it is listed in O-23 and must be checked before the first real
send. Anything unrecognised is RETRYABLE, never OK (ADR-0029 §2). The access key is
never included in an error message.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from sukoon.services.notifications.policy import Outcome
from sukoon.services.notifications.providers.base import OutgoingMessage, SendResult

DEFAULT_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v23.0"  # (verify) — configurable: WHATSAPP_API_VERSION

# (verify every code — O-23)
_ACCOUNT_BROKEN_CODES = {
    190,     # access token invalid or expired
    131031,  # business account locked
    131042,  # payment / eligibility problem on the account
    133010,  # phone number not registered with the Cloud API
    368,     # temporarily blocked for policy violations
}
_RETRYABLE_CODES = {4, 80007, 130429, 131016, 131048, 131056, 133004}  # rate limits, service
_PERMANENT_CODES = {
    100,     # invalid parameter
    131008,  # required parameter missing
    131009,  # parameter value invalid
    131026,  # message undeliverable (not on WhatsApp, etc.)
    131047,  # re-engagement required
    131051,  # unsupported message type
    132000,  # template parameter count mismatch
    132001,  # template does not exist / not approved
    132005,  # template text too long
    132007,  # template format character policy
    132012,  # template parameter format mismatch
    132015,  # template paused
    132016,  # template disabled
}


@dataclass
class MetaProvider:
    access_key: str | None
    phone_number_id: str | None
    api_version: str = DEFAULT_API_VERSION
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 20.0
    name: str = "meta"

    # --- public ------------------------------------------------------------------------

    def send(self, message: OutgoingMessage) -> SendResult:
        missing = self._missing()
        if missing:
            return missing
        components: list[dict] = []
        if message.document is not None:
            media = self._upload_pdf(message.document, message.document_name or "statement.pdf")
            if media.outcome is not Outcome.OK:
                return media
            components.append({"type": "header", "parameters": [{
                "type": "document",
                "document": {"id": media.message_id, "filename": message.document_name}}]})
        components.append({"type": "body", "parameters": [
            {"type": "text", "text": p} for p in message.params]})
        body = {
            "messaging_product": "whatsapp",
            "to": message.to.lstrip("+"),
            "type": "template",
            "template": {"name": message.template, "language": {"code": message.language},
                         "components": components},
        }
        status, data, outcome = self._request(
            "POST", f"/{self.phone_number_id}/messages",
            data=json.dumps(body).encode(), content_type="application/json")
        if outcome is not None:
            return outcome
        try:
            return SendResult(Outcome.OK, message_id=data["messages"][0]["id"])
        except (KeyError, IndexError, TypeError):
            # a 2xx we can't read is not proof of sending
            return SendResult(Outcome.RETRYABLE, error="WhatsApp gave an unreadable reply")

    def check(self) -> SendResult:
        missing = self._missing()
        if missing:
            return missing
        _status, _data, outcome = self._request(
            "GET", f"/{self.phone_number_id}?fields=display_phone_number")
        return outcome or SendResult(Outcome.OK)

    # --- internals ------------------------------------------------------------------------

    def _missing(self) -> SendResult | None:
        if not self.access_key:
            return SendResult(Outcome.ACCOUNT_BROKEN, error="No WhatsApp access key is set")
        if not self.phone_number_id:
            return SendResult(Outcome.ACCOUNT_BROKEN, error="No WhatsApp phone number ID is set")
        return None

    def _upload_pdf(self, pdf: bytes, filename: str) -> SendResult:
        boundary = uuid.uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="messaging_product"\r\n\r\n'
            f"whatsapp\r\n".encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\n'
            f"application/pdf\r\n".encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"'
            f"\r\nContent-Type: application/pdf\r\n\r\n".encode() + pdf + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        _status, data, outcome = self._request(
            "POST", f"/{self.phone_number_id}/media", data=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}")
        if outcome is not None:
            return outcome
        media_id = (data or {}).get("id")
        if not media_id:
            return SendResult(Outcome.RETRYABLE, error="WhatsApp didn't return the uploaded file")
        return SendResult(Outcome.OK, message_id=media_id)

    def _request(
        self, method: str, path: str, *, data: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int | None, dict | None, SendResult | None]:
        url = f"{self.base_url}/{self.api_version}{path}"
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.access_key}")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
                return resp.status, _json(raw), None
        except urllib.error.HTTPError as exc:
            payload = _json(exc.read()) or {}
            return exc.code, payload, classify(exc.code, payload)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return None, None, SendResult(Outcome.NO_CONNECTION,
                                          error="No internet connection to WhatsApp")


def _json(raw: bytes) -> dict | None:
    try:
        value = json.loads(raw or b"null")
        return value if isinstance(value, dict) else None
    except ValueError:
        return None


def classify(status: int, payload: dict) -> SendResult:
    """An HTTP error response -> one of ADR-0029's outcomes, with a message safe to show."""
    err = payload.get("error") if isinstance(payload, dict) else None
    err = err if isinstance(err, dict) else {}
    code = err.get("code")
    words = str(err.get("error_user_msg") or err.get("message") or f"HTTP {status}")[:200]
    if code in _ACCOUNT_BROKEN_CODES or status in (401, 403):
        return SendResult(Outcome.ACCOUNT_BROKEN, error=words)
    if code in _PERMANENT_CODES:
        return SendResult(Outcome.PERMANENT, error=words)
    if code in _RETRYABLE_CODES or status == 429 or status >= 500:
        return SendResult(Outcome.RETRYABLE, error=words)
    return SendResult(Outcome.RETRYABLE, error=words)  # unknown: retry, never "sent"
