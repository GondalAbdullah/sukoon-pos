"""The desktop window's waiting logic (ADR-0035 §6). The window itself needs a desktop session
and is exercised on Windows; what decides whether the owner sees Sukoon, a 'starting' page or
an error is plain Python, tested here."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sukoon import desktop


class _Handler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):  # noqa: N802
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    started = []

    def start(status):
        handler = type("H", (_Handler,), {"status": status})
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}/"

    yield start
    for httpd in started:
        httpd.shutdown()


@pytest.mark.parametrize("status,ready", [(200, True), (302, True), (403, True), (500, False),
                                          (503, False)])
def test_any_answer_short_of_a_server_error_means_sukoon_is_up(server, status, ready):
    assert desktop.server_ready(server(status)) is ready


def test_nothing_listening_is_not_ready():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # closed again: nothing listens there
    assert desktop.server_ready(f"http://127.0.0.1:{port}/", timeout=0.5) is False


def test_the_window_waits_for_a_server_that_is_still_starting():
    answers = iter([False, False, False, True])
    now = [0.0]
    assert desktop.wait_for_server("x", 90, ready=lambda _: next(answers),
                                   sleep=lambda s: now.__setitem__(0, now[0] + s),
                                   clock=lambda: now[0]) is True
    assert now[0] == 1.5  # three half-second waits, then Sukoon


def test_the_window_gives_up_and_explains_when_the_server_never_comes():
    now = [0.0]
    assert desktop.wait_for_server("x", 90, ready=lambda _: False,
                                   sleep=lambda s: now.__setitem__(0, now[0] + s),
                                   clock=lambda: now[0]) is False
    assert 90 <= now[0] <= 90.5
    assert "restart" in desktop.NOT_RUNNING_HTML and "safe" in desktop.NOT_RUNNING_HTML


def test_the_window_keeps_its_cookies_so_the_till_keeps_its_name(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.storage_path() == tmp_path / "Sukoon" / "window"
