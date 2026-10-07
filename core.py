"""Download logic for YTGrab. No UI code here, so it can be tested on its own."""
from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass, asdict
from typing import Callable

import yt_dlp


# ---------------------------------------------------------------- helpers ---

def _bundled_dir() -> str | None:
    """Folder PyInstaller unpacks into when running as a built app."""
    return getattr(sys, "_MEIPASS", None)


def find_ffmpeg() -> str | None:
    """ffmpeg merges the best video + audio streams and makes MP3s."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def find_deno() -> str | None:
    """YouTube now needs a JavaScript runtime (Deno) for full quality lists."""
    base = _bundled_dir()
    if base:  # inside the built app: use the copy we shipped
        for name in ("deno.exe", "deno"):
            p = os.path.join(base, "deno_bin", name)
            if os.path.exists(p):
                return p
    try:
        import deno
        path = deno.find_deno_bin()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    return shutil.which("deno")


def base_options() -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "noplaylist": True}
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    deno_path = find_deno()
    if deno_path:
        opts["js_runtimes"] = {"deno": {"path": deno_path}}
    return opts


# YouTube regularly blocks one "player client" or another, which shows up as
# HTTP 403. We try yt-dlp's default first, then a few known-good alternatives.
CLIENT_FALLBACKS: list[list[str] | None] = [
    None,                         # yt-dlp's current default
    ["tv", "web_safari"],
    ["android", "ios"],
    ["web_embedded", "mweb"],
]


def _is_blocked(e: Exception) -> bool:
    msg = str(e)
    return "403" in msg or "Forbidden" in msg


# ---------------------------------------------------------------- formats ---

@dataclass
class Choice:
    id: str              # "v2160" / "a320"
    kind: str            # "video" or "audio"
    title: str           # "2160p" / "MP3 320 kbps"
    detail: str          # "4K, 60 fps" / "Best quality"
    size: int | None     # estimated bytes, None if unknown
    height: int | None = None
    kbps: int | None = None


AUDIO_LEVELS = [(320, "Best quality"), (192, "Smaller file"), (128, "Smallest file")]
NAMED = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}


def _size(f: dict, duration: float | None) -> int | None:
    s = f.get("filesize") or f.get("filesize_approx")
    if not s and duration and f.get("tbr"):
        s = f["tbr"] * 1000 / 8 * duration
    return int(s) if s else None


def build_choices(info: dict) -> list[Choice]:
    """Every available video resolution (highest first), then MP3 levels."""
    duration = info.get("duration")
    formats = info.get("formats") or []

    audio = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    best_audio = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    audio_size = _size(best_audio, duration) if best_audio else 0

    by_height: dict[int, dict] = {}
    for f in formats:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        cur = by_height.get(h)
        key = (f.get("fps") or 0, f.get("tbr") or 0)
        if cur is None or key > (cur.get("fps") or 0, cur.get("tbr") or 0):
            by_height[h] = f

    choices: list[Choice] = []
    for h in sorted(by_height, reverse=True):
        f = by_height[h]
        parts = []
        if h in NAMED:
            parts.append(NAMED[h])
        fps = f.get("fps") or 0
        if fps > 30:
            parts.append(f"{int(round(fps))} fps")
        vsize = _size(f, duration)
        size = vsize + (audio_size or 0) if vsize else None
        choices.append(Choice(f"v{h}", "video", f"{h}p", ", ".join(parts), size, height=h))

    for kbps, detail in AUDIO_LEVELS:
        size = int(kbps * 1000 / 8 * duration) if duration else None
        choices.append(Choice(f"a{kbps}", "audio", f"MP3 {kbps} kbps", detail, size, kbps=kbps))
    return choices


def summarize(info: dict) -> dict:
    """What the UI needs to show about a video."""
    return {
        "title": info.get("title") or "Untitled video",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
        "choices": [asdict(c) for c in build_choices(info)],
    }


def fetch_info(url: str) -> dict:
    last_error: Exception | None = None
    for clients in CLIENT_FALLBACKS:
        opts = {**base_options(), "skip_download": True}
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            if not _is_blocked(e):
                raise
            last_error = e
    raise RuntimeError("YouTube refused the request. Wait a minute, then try again.") from last_error


# --------------------------------------------------------------- download ---

def download_options(choice: Choice, out_dir: str) -> dict:
    opts = base_options()
    if choice.kind == "audio":
        opts["outtmpl"] = os.path.join(out_dir, "%(title)s.%(ext)s")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(choice.kbps or 320),
        }, {"key": "FFmpegMetadata"}]
    else:
        h = choice.height
        opts["outtmpl"] = os.path.join(out_dir, "%(title)s [%(height)sp].%(ext)s")
        # Exact height first; fall back to the best at or below it.
        opts["format"] = (
            f"bv*[height={h}]+ba/b[height={h}]/"
            f"bv*[height<={h}]+ba/b[height<={h}]"
        )
        # MP4 plays everywhere. 4K/8K is often VP9/AV1 only, which goes into MKV.
        opts["merge_output_format"] = "mp4/mkv"
        opts["format_sort"] = ["res", "fps", "vcodec:h264", "acodec:m4a"] if h <= 1080 else ["res", "fps"]
    return opts


class Cancelled(Exception):
    pass


def download(url: str, choice: Choice, out_dir: str,
             on_progress: Callable[[dict], None] | None = None,
             cancel: threading.Event | None = None) -> str:
    """Runs the download and returns the saved file's path.

    on_progress gets {"phase", "fraction" (0..1, whole job), "speed", "eta"}.
    Video jobs download two streams (picture, then sound), weighted 90/10.
    """
    weights = [0.9, 0.1] if choice.kind == "video" else [1.0]
    state = {"stage": 0}

    def emit(**kw) -> None:
        if on_progress:
            on_progress(kw)

    def hook(d: dict) -> None:
        if cancel and cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled("Cancelled")
        stage = min(state["stage"], len(weights) - 1)
        done_before = sum(weights[:stage])
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes") or 0) / total if total else 0.0
            emit(phase="downloading",
                 fraction=min(done_before + weights[stage] * frac, 0.99),
                 speed=d.get("speed"), eta=d.get("eta"))
        elif d["status"] == "finished":
            state["stage"] += 1
            if state["stage"] >= len(weights):
                emit(phase="finishing", fraction=1.0, speed=None, eta=None)

    last_error: Exception | None = None
    for i, clients in enumerate(CLIENT_FALLBACKS):
        state["stage"] = 0
        opts = download_options(choice, out_dir)
        opts["progress_hooks"] = [hook]
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        if i:
            emit(phase="retrying", fraction=0.0, speed=None, eta=None, attempt=i + 1)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return _saved_path(info, ydl)
        except yt_dlp.utils.DownloadCancelled:
            raise Cancelled()
        except yt_dlp.utils.DownloadError as e:
            if cancel and cancel.is_set():
                raise Cancelled()
            if not _is_blocked(e):
                raise
            last_error = e
    raise RuntimeError("YouTube refused the download. Wait a minute, then try again.") from last_error


def _saved_path(info: dict, ydl: yt_dlp.YoutubeDL) -> str:
    for d in info.get("requested_downloads") or []:
        if d.get("filepath"):
            return d["filepath"]
    return ydl.prepare_filename(info)
