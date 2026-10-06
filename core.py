"""Download logic for YTGrab. No UI code here, so it can be tested on its own."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
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


# ---------------------------------------------------------------- formats ---

@dataclass
class Choice:
    label: str          # what the user sees in the dropdown
    height: int | None  # None = audio only (MP3)


def _fmt_label(height: int, fps: float | None) -> str:
    names = {4320: "8K", 2160: "4K", 1440: "2K"}
    label = f"{height}p"
    if height in names:
        label += f" ({names[height]})"
    if fps and fps > 30:
        label += f" {int(fps)}fps"
    return label


def build_choices(info: dict) -> list[Choice]:
    """Every available video resolution, highest first, then MP3 at the end."""
    best_fps: dict[int, float] = {}
    for f in info.get("formats") or []:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        best_fps[h] = max(best_fps.get(h, 0), f.get("fps") or 0)
    choices = [Choice(_fmt_label(h, best_fps[h]), h) for h in sorted(best_fps, reverse=True)]
    choices.append(Choice("Audio only (MP3)", None))
    return choices


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
    raise RuntimeError("YouTube refused the request (403). Try again in a few minutes.") from last_error


# --------------------------------------------------------------- download ---

def download_options(choice: Choice, out_dir: str, mp3_kbps: str = "320") -> dict:
    opts = base_options()
    opts["outtmpl"] = os.path.join(out_dir, "%(title)s [%(height)sp].%(ext)s")
    if choice.height is None:
        opts["outtmpl"] = os.path.join(out_dir, "%(title)s.%(ext)s")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": mp3_kbps,
        }, {"key": "FFmpegMetadata"}]
    else:
        h = choice.height
        # Exact height first; fall back to the best at or below it.
        opts["format"] = (
            f"bv*[height={h}]+ba/b[height={h}]/"
            f"bv*[height<={h}]+ba/b[height<={h}]"
        )
        # MP4 plays everywhere (QuickTime, Windows Photos, editing software).
        # 4K/8K often only exists as VP9/AV1, which yt-dlp re-wraps into MKV if MP4 can't hold it.
        opts["merge_output_format"] = "mp4/mkv"
        opts["format_sort"] = ["res", "fps", "vcodec:h264", "acodec:m4a"] if h <= 1080 else ["res", "fps"]
    return opts


def download(url: str, choice: Choice, out_dir: str,
             on_progress: Callable[[float, str], None] | None = None) -> None:
    """Runs the download. on_progress(fraction 0..1, status text)."""

    def hook(d: dict) -> None:
        if not on_progress:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = done / total if total else 0.0
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            on_progress(frac, f"Downloading… {frac*100:.0f}%  {speed}  ETA {eta}".strip())
        elif d["status"] == "finished":
            on_progress(1.0, "Processing (merging / converting)…")

    last_error: Exception | None = None
    for i, clients in enumerate(CLIENT_FALLBACKS):
        opts = download_options(choice, out_dir)
        opts["progress_hooks"] = [hook]
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        if i and on_progress:
            on_progress(0.0, f"YouTube blocked that attempt — retrying ({i + 1}/{len(CLIENT_FALLBACKS)})…")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return
        except yt_dlp.utils.DownloadError as e:
            if not _is_blocked(e):
                raise
            last_error = e
    raise RuntimeError(
        "YouTube refused the download (403) after several tries. "
        "Try again in a few minutes, or rebuild the app to get the newest downloader."
    ) from last_error


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
