"""The Sukoon window on the shop PC (ADR-0001 pywebview; ADR-0035 §6).

The window is only a window. The server is a separate boot task that starts with Windows
(ADR-0035 §1), so closing this never stops the shop — other tills keep selling. When the owner
opens Sukoon right after the PC boots, the server may still be starting, so the window shows a
"starting" page and waits for it rather than an error.

``webview`` is imported only inside ``main``: the waiting logic is plain Python and is tested on
any platform; the window itself is exercised on Windows.
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

SERVER_URL = os.environ.get("SUKOON_URL", "http://127.0.0.1:5000/")
WAIT_SECONDS = 90

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:"Segoe UI",system-ui,sans-serif;background:#FAF9F6;color:#1C1C1E}}
div{{max-width:460px;text-align:center;padding:24px}}
.logo{{font-size:28px;font-weight:800;letter-spacing:-.03em;margin-bottom:18px}}
.logo span{{color:#0E6B57}} h1{{font-size:18px;margin:0 0 8px}}
p{{color:#6B6A66;font-size:14px;line-height:1.5;margin:0}}</style></head>
<body><div><div class="logo">suk<span>oon</span></div>
<h1>{title}</h1><p>{body}</p></div></body></html>"""

STARTING_HTML = _PAGE.format(
    title="Starting Sukoon…",
    body="This takes a few seconds after the computer has just been switched on.")

NOT_RUNNING_HTML = _PAGE.format(
    title="Sukoon's server isn't running",
    body="Close this window and restart the computer. If you still see this message after "
         "restarting, call the person who looks after Sukoon for the shop. Sales already "
         "made are safe.")


def server_ready(url: str, timeout: float = 2.0) -> bool:
    """The server answers at all. Any response below 500 counts — the setup screen and the
    sign-in redirect are both a working server."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def wait_for_server(url: str, seconds: float, *,
                    ready: Callable[[str], bool] = server_ready,
                    sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> bool:
    deadline = clock() + seconds
    while True:
        if ready(url):
            return True
        if clock() >= deadline:
            return False
        sleep(0.5)


def storage_path() -> Path:
    """Where the window keeps its cookies. pywebview's default *private mode* forgets them
    when the window closes — and the till's name lives in a cookie (ADR-0023), so the owner
    would be asked to name the till every time Sukoon was opened."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Sukoon" / "window"


WEBVIEW_SETTINGS: dict[str, bool] = {
    # Without this, pywebview silently discards downloads: the label sheet's "Download PDF"
    # did nothing at all, with no message and no file (found on the VM, 2026-09-18). With it,
    # the window shows its own download bar and saves to the signed-in user's Downloads folder.
    "ALLOW_DOWNLOADS": True,
    # A link that opens "in a new window" would otherwise open the system browser, which has no
    # Sukoon session — the Khata statement asked the owner to sign in again just to get a PDF.
    "OPEN_EXTERNAL_LINKS_IN_BROWSER": False,
}


def main() -> None:  # pragma: no cover — needs a desktop session; exercised on Windows
    import webview

    webview.settings.update(WEBVIEW_SETTINGS)

    window = webview.create_window("Sukoon", html=STARTING_HTML, maximized=True,
                                   min_size=(1024, 700))

    def navigate():
        if wait_for_server(SERVER_URL, WAIT_SECONDS):
            window.load_url(SERVER_URL)
        else:
            window.load_html(NOT_RUNNING_HTML)

    path = storage_path()
    path.mkdir(parents=True, exist_ok=True)
    webview.start(navigate, private_mode=False, storage_path=str(path))


if __name__ == "__main__":  # pragma: no cover
    main()
