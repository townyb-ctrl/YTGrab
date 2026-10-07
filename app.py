"""YTGrab — a clean YouTube downloader for Mac and Windows.

The window is a native web view (WebKit on Mac, Edge WebView2 on Windows)
showing ui/index.html. The page talks to the Api class below.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import webview

import core

APP_NAME = "YTGrab"


# --------------------------------------------------------------- settings ---

def _settings_file() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / APP_NAME / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_file().read_text())
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        f = _settings_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data))
    except Exception:
        pass


def default_folder() -> str:
    d = Path.home() / "Downloads"
    return str(d if d.exists() else Path.home())


def resource(path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path)


# --------------------------------------------------------------------- api ---

class Api:
    """Every public method here can be called from the page as
    `await pywebview.api.<name>(...)`."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._choices: dict[str, core.Choice] = {}
        self._cancel = threading.Event()
        s = load_settings()
        folder = s.get("folder")
        self._folder = folder if folder and os.path.isdir(folder) else default_folder()

    def attach(self, window: webview.Window) -> None:
        self._window = window

    # -- state
    def get_state(self) -> dict:
        return {
            "folder": self._folder,
            "folderName": os.path.basename(self._folder.rstrip("/\\")) or self._folder,
            "platform": sys.platform,
            "ffmpeg": bool(core.find_ffmpeg()),
        }

    def choose_folder(self) -> dict:
        assert self._window
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=self._folder)
        if result:
            self._folder = result[0] if isinstance(result, (list, tuple)) else result
            save_settings({"folder": self._folder})
        return self.get_state()

    # -- fetch
    def fetch(self, url: str) -> dict:
        try:
            info = core.fetch_info(url.strip())
            summary = core.summarize(info)
            self._choices = {c["id"]: core.Choice(**c) for c in summary["choices"]}
            return {"ok": True, **summary}
        except Exception as e:
            return {"ok": False, "error": friendly_error(e)}

    # -- download (runs in the background, reports through window.ytg.*)
    def download(self, url: str, choice_id: str) -> None:
        choice = self._choices.get(choice_id)
        if not choice:
            self._js("ytg.onError", "Pick a quality first.")
            return
        self._cancel.clear()
        threading.Thread(target=self._run, args=(url.strip(), choice), daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, url: str, choice: core.Choice) -> None:
        try:
            path = core.download(url, choice, self._folder,
                                 on_progress=lambda p: self._js("ytg.onProgress", p),
                                 cancel=self._cancel)
            self._js("ytg.onDone", {"path": path, "name": os.path.basename(path)})
        except core.Cancelled:
            self._js("ytg.onCancelled", None)
        except Exception as e:
            self._js("ytg.onError", friendly_error(e))

    # -- after download
    def reveal(self, path: str) -> None:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _js(self, fn: str, payload) -> None:
        if self._window:
            self._window.evaluate_js(f"{fn}({json.dumps(payload)})")


def friendly_error(e: Exception) -> str:
    msg = str(e).replace("ERROR: ", "").strip()
    low = msg.lower()
    if "is not a valid url" in low or "unsupported url" in low:
        return "That doesn't look like a YouTube link. Copy the address from the video page and paste it again."
    if "private video" in low:
        return "This video is private, so it can't be downloaded."
    if "sign in to confirm your age" in low or "age-restricted" in low:
        return "This video is age-restricted, so YouTube won't allow the download."
    if "video unavailable" in low:
        return "This video is unavailable. It may have been removed or blocked in your country."
    if "unable to download webpage" in low or "getaddrinfo" in low or "timed out" in low:
        return "Couldn't reach YouTube. Check your internet connection and try again."
    if "ffmpeg" in low:
        return "A built-in tool (ffmpeg) is missing. Download the latest version of YTGrab."
    return msg if len(msg) < 180 else msg[:177] + "…"


def main() -> None:
    api = Api()
    window = webview.create_window(
        APP_NAME,
        url=resource(os.path.join("ui", "index.html")),
        js_api=api,
        width=500,
        height=800,
        min_size=(440, 680),
        background_color="#F4F5F7",
    )
    api.attach(window)
    webview.start(debug=bool(os.environ.get("YTGRAB_DEBUG")))


if __name__ == "__main__":
    main()
