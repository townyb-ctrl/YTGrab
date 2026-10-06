"""YTGrab — simple YouTube downloader for Mac and Windows."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

import core

APP_NAME = "YTGrab"


def default_folder() -> str:
    d = Path.home() / "Downloads"
    return str(d if d.exists() else Path.home())


def open_folder(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title(APP_NAME)
        self.geometry("620x380")
        self.minsize(520, 360)

        self.events: queue.Queue = queue.Queue()  # worker threads -> UI
        self.choices: list[core.Choice] = []
        self.out_dir = default_folder()

        pad = {"padx": 20}

        ctk.CTkLabel(self, text=APP_NAME, font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(18, 4), **pad, anchor="w")

        # 1. Link
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=6, **pad)
        self.url = ctk.CTkEntry(row, placeholder_text="Paste a YouTube link…", height=36)
        self.url.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda _e: self.on_fetch())
        self.fetch_btn = ctk.CTkButton(row, text="Get qualities", width=120, height=36, command=self.on_fetch)
        self.fetch_btn.pack(side="left", padx=(8, 0))

        self.title_lbl = ctk.CTkLabel(self, text="", anchor="w", wraplength=560, justify="left")
        self.title_lbl.pack(fill="x", **pad)

        # 2. Quality
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=6, **pad)
        ctk.CTkLabel(row, text="Quality:", width=70, anchor="w").pack(side="left")
        self.quality = ctk.CTkOptionMenu(row, values=["—"], state="disabled", width=220)
        self.quality.pack(side="left")

        # 3. Save to
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=6, **pad)
        ctk.CTkLabel(row, text="Save to:", width=70, anchor="w").pack(side="left")
        self.folder_lbl = ctk.CTkLabel(row, text=self.out_dir, anchor="w")
        self.folder_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Change…", width=90, command=self.on_choose_folder).pack(side="left")

        # 4. Download
        self.dl_btn = ctk.CTkButton(self, text="Download", height=40, state="disabled",
                                    font=ctk.CTkFont(size=15, weight="bold"), command=self.on_download)
        self.dl_btn.pack(fill="x", pady=(12, 6), **pad)

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=4, **pad)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", **pad)
        self.status = ctk.CTkLabel(row, text="Paste a link to start.", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        self.open_btn = ctk.CTkButton(row, text="Open folder", width=110,
                                      command=lambda: open_folder(self.out_dir))

        if not core.find_ffmpeg():
            self.status.configure(text="Warning: ffmpeg not found — high-res and MP3 won't work.")

        self.after(100, self.poll_events)

    # ------------------------------------------------------------ actions --

    def on_choose_folder(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_dir)
        if d:
            self.out_dir = d
            self.folder_lbl.configure(text=d)

    def on_fetch(self) -> None:
        url = self.url.get().strip()
        if not url:
            self.status.configure(text="Paste a YouTube link first.")
            return
        self.set_busy(True, "Checking available qualities…")
        self.quality.configure(state="disabled", values=["—"])
        self.quality.set("—")
        self.dl_btn.configure(state="disabled")
        self.open_btn.pack_forget()
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url: str) -> None:
        try:
            info = core.fetch_info(url)
            self.events.put(("info", info))
        except Exception as e:
            self.events.put(("error", _clean_error(e)))

    def on_download(self) -> None:
        label = self.quality.get()
        choice = next((c for c in self.choices if c.label == label), None)
        if not choice:
            return
        self.set_busy(True, "Starting download…")
        self.progress.set(0)
        self.open_btn.pack_forget()
        url = self.url.get().strip()
        threading.Thread(target=self._download_worker, args=(url, choice), daemon=True).start()

    def _download_worker(self, url: str, choice: core.Choice) -> None:
        try:
            core.download(url, choice, self.out_dir,
                          on_progress=lambda f, s: self.events.put(("progress", (f, s))))
            self.events.put(("done", None))
        except Exception as e:
            self.events.put(("error", _clean_error(e)))

    # ------------------------------------------------- thread -> UI bridge --

    def poll_events(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "info":
                    self.choices = core.build_choices(data)
                    labels = [c.label for c in self.choices]
                    self.quality.configure(values=labels, state="normal")
                    self.quality.set(labels[0])  # highest resolution by default
                    self.title_lbl.configure(text=data.get("title", ""))
                    self.set_busy(False, f"{len(labels) - 1} video qualities found. Highest is selected.")
                    self.dl_btn.configure(state="normal")
                elif kind == "progress":
                    frac, text = data
                    self.progress.set(frac)
                    self.status.configure(text=text)
                elif kind == "done":
                    self.progress.set(1)
                    self.set_busy(False, "Done ✓")
                    self.dl_btn.configure(state="normal")
                    self.open_btn.pack(side="left")
                elif kind == "error":
                    self.set_busy(False, f"Error: {data}")
                    if self.choices:
                        self.dl_btn.configure(state="normal")
        except queue.Empty:
            pass
        self.after(100, self.poll_events)

    def set_busy(self, busy: bool, text: str) -> None:
        self.status.configure(text=text)
        self.fetch_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.dl_btn.configure(state="disabled")


def _clean_error(e: Exception) -> str:
    msg = str(e).replace("ERROR: ", "")
    return msg if len(msg) < 160 else msg[:157] + "…"


if __name__ == "__main__":
    App().mainloop()
