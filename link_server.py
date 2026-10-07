"""Tiny local server so the YTGrab Chrome extension can hand links to the app.

It only listens on this computer (127.0.0.1), only accepts YouTube links,
and refuses requests coming from ordinary web pages.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

PORT = 47681
SCHEME = "ytgrab"


def is_youtube(url: str) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    host = (u.hostname or "").lower()
    return u.scheme in ("http", "https") and (
        host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"))


def link_from_scheme(arg: str) -> str | None:
    """'ytgrab://open?url=<link>' -> '<link>' (used when Chrome launches the app)."""
    if not arg.lower().startswith(SCHEME + "://"):
        return None
    url = (parse_qs(urlparse(arg).query).get("url") or [""])[0]
    return url if is_youtube(url) else None


def _origin_allowed(origin: str | None) -> bool:
    # Browsers always send Origin on cross-site POSTs. Web pages get refused;
    # the extension (chrome-extension://…) and local tools (no Origin) are fine.
    return origin is None or origin.startswith("chrome-extension://")


def start(on_link: Callable[[str], None], port: int = PORT) -> ThreadingHTTPServer | None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep quiet
            pass

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/ping" and _origin_allowed(self.headers.get("Origin")):
                self._send(200, {"app": "YTGrab"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/open":
                return self._send(404, {"error": "not found"})
            if not _origin_allowed(self.headers.get("Origin")):
                return self._send(403, {"error": "forbidden"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > 4096:
                return self._send(413, {"error": "too large"})
            try:
                url = str(json.loads(self.rfile.read(length) or b"{}").get("url", "")).strip()
            except Exception:
                return self._send(400, {"error": "bad request"})
            if not is_youtube(url):
                return self._send(400, {"error": "not a YouTube link"})
            on_link(url)
            self._send(200, {"ok": True})

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        return None  # port busy (e.g. a second copy of the app) — the app still works
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def register_windows_scheme(exe_path: str) -> None:
    """Lets Chrome open YTGrab via ytgrab:// links. Per-user, no admin needed."""
    import winreg  # type: ignore[import-not-found]
    base = rf"Software\Classes\{SCHEME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:YTGrab")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe_path}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe_path}" "%1"')
