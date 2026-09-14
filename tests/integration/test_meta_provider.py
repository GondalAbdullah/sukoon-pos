"""Meta adapter against a local stub of the Graph API — real HTTP, no real account
(ADR-0027, ADR-0029 §2). The error-code mapping itself is unverified against Meta (O-23);
these tests prove the adapter classifies what it's told to, sends the right shape, and
never leaks the key."""
from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon.services.notifications.policy import Outcome
from sukoon.services.notifications.providers.base import OutgoingMessage
from sukoon.services.notifications.providers.meta import MetaProvider

KEY = "EAAG-super-secret-key-123"


class Stub:
    def __init__(self):
        self.requests: list[dict] = []
        self.responses: list[tuple[int, dict | None, float]] = []  # (status, body, delay)


@pytest.fixture
def stub():
    state = Stub()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self):
            length = int(self.headers.get("Content-Length") or 0)
            state.requests.append({"method": self.command, "path": self.path,
                                   "auth": self.headers.get("Authorization"),
                                   "type": self.headers.get("Content-Type"),
                                   "body": self.rfile.read(length) if length else b""})
            status, body, delay = state.responses.pop(0) if state.responses else (
                200, {"messages": [{"id": "wamid.OK"}]}, 0)
            time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode() if body is not None else b"")

        do_GET = do_POST = _reply

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


def provider(stub, **kw):
    return MetaProvider(access_key=KEY, phone_number_id="1234567890", base_url=stub.url,
                        api_version="v99.0", timeout_seconds=kw.pop("timeout", 2.0), **kw)


MSG = OutgoingMessage(to="+923005541298", template="sukoon_credit_sale", language="en",
                      params=["1 item", "Rs 600"], text="…")


def test_an_accepted_message_is_ok_and_shaped_as_a_template(stub):
    r = provider(stub).send(MSG)
    assert (r.outcome, r.message_id) == (Outcome.OK, "wamid.OK")
    [req] = stub.requests
    assert req["path"] == "/v99.0/1234567890/messages" and req["auth"] == f"Bearer {KEY}"
    body = json.loads(req["body"])
    assert body["to"] == "923005541298" and body["type"] == "template"
    assert body["template"]["name"] == "sukoon_credit_sale"
    assert body["template"]["components"] == [{"type": "body", "parameters": [
        {"type": "text", "text": "1 item"}, {"type": "text", "text": "Rs 600"}]}]


def test_a_statement_uploads_the_pdf_first_and_attaches_it(stub):
    stub.responses = [(200, {"id": "media-77"}, 0), (200, {"messages": [{"id": "wamid.S"}]}, 0)]
    msg = OutgoingMessage(to="+923005541298", template="sukoon_statement", language="en",
                          params=["September 2026"], text="…", document=b"%PDF-1.4 fake",
                          document_name="Khata statement September 2026.pdf")
    assert provider(stub).send(msg).outcome is Outcome.OK
    upload, send = stub.requests
    assert upload["path"].endswith("/media") and b"%PDF-1.4 fake" in upload["body"]
    assert upload["type"].startswith("multipart/form-data")
    header = json.loads(send["body"])["template"]["components"][0]
    assert header["parameters"][0]["document"] == {
        "id": "media-77", "filename": "Khata statement September 2026.pdf"}


@pytest.mark.parametrize("status,body,outcome", [
    (401, {"error": {"code": 190, "message": "Error validating access token"}},
     Outcome.ACCOUNT_BROKEN),
    (400, {"error": {"code": 131042, "message": "Payment issue"}}, Outcome.ACCOUNT_BROKEN),
    (429, {"error": {"code": 130429, "message": "Rate limit hit"}}, Outcome.RETRYABLE),
    (503, {"error": {"message": "Service unavailable"}}, Outcome.RETRYABLE),
    (400, {"error": {"code": 131026, "message": "Message undeliverable"}}, Outcome.PERMANENT),
    (400, {"error": {"code": 132001, "message": "Template does not exist"}}, Outcome.PERMANENT),
    (400, {"error": {"code": 999999, "message": "Something new"}}, Outcome.RETRYABLE),
    (418, None, Outcome.RETRYABLE),
])
def test_error_responses_are_classified(stub, status, body, outcome):
    stub.responses = [(status, body, 0)]
    r = provider(stub).send(MSG)
    assert r.outcome is outcome and KEY not in (r.error or "")


def test_a_2xx_without_a_message_id_is_not_proof_of_sending(stub):
    stub.responses = [(200, {"unexpected": True}, 0)]
    assert provider(stub).send(MSG).outcome is Outcome.RETRYABLE


def test_nobody_listening_is_no_connection(stub):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # a port nobody listens on once closed
    p = MetaProvider(access_key=KEY, phone_number_id="1", base_url=f"http://127.0.0.1:{port}")
    r = p.send(MSG)
    assert r.outcome is Outcome.NO_CONNECTION and KEY not in r.error


def test_a_timeout_before_any_response_is_no_connection(stub):
    stub.responses = [(200, {"messages": [{"id": "late"}]}, 1.5)]
    assert provider(stub, timeout=0.3).send(MSG).outcome is Outcome.NO_CONNECTION


def test_missing_key_or_number_id_is_account_broken_without_calling_meta(stub):
    r = MetaProvider(access_key=None, phone_number_id="1", base_url=stub.url).send(MSG)
    assert (r.outcome, r.error) == (Outcome.ACCOUNT_BROKEN, "No WhatsApp access key is set")
    r = MetaProvider(access_key=KEY, phone_number_id=None, base_url=stub.url).check()
    assert r.error == "No WhatsApp phone number ID is set" and stub.requests == []


def test_check_reads_the_number_and_sends_nothing(stub):
    stub.responses = [(200, {"display_phone_number": "+92 300 0000000"}, 0)]
    assert provider(stub).check().outcome is Outcome.OK
    [req] = stub.requests
    assert req["method"] == "GET" and "messages" not in req["path"]
