# YTGrab

Paste a YouTube link → pick a quality (highest is selected by default) or **Audio only (MP3)** → Download.

Works on Mac and Windows. ffmpeg (for merging HD video + audio and making MP3s) and Deno (which YouTube now requires) are bundled inside the app, so users install nothing extra.

---

## 1. Try it on your Mac right now (5 minutes)

```bash
cd ytgrab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

> If you get `No module named '_tkinter'`, run `brew install python-tk` and repeat.

## 2. Build the real apps (Mac + Windows)

You can't build a Windows .exe on a Mac, so GitHub builds both for you, free.

1. Create a new GitHub repo and push this folder to it.
2. Go to the repo's **Actions** tab → **Build YTGrab** → **Run workflow**.
3. When it finishes (~5 min), download **YTGrab-mac** and **YTGrab-windows** from the bottom of the run page.

It also rebuilds every Monday with the newest yt-dlp, because YouTube changes often and old versions stop working.

**Mac only, build locally instead:** `pyinstaller YTGrab.spec` → app is in `dist/YTGrab.app`.

## 3. First launch for your users

The app isn't code-signed (that costs money: Apple $99/yr, Windows certificate ~$200+/yr), so:

- **Mac:** right-click YTGrab → **Open** → **Open**. Only needed the first time.
- **Windows:** on the blue SmartScreen box, click **More info** → **Run anyway**.

## Files

| File | What it is |
|---|---|
| `app.py` | The window (buttons, dropdown, progress bar) |
| `core.py` | The downloading logic (uses yt-dlp) |
| `YTGrab.spec` | Packaging recipe for PyInstaller |
| `.github/workflows/build.yml` | Builds Mac + Windows apps on GitHub |

## Notes

- 4K/8K videos usually save as `.mkv` (YouTube only offers those in formats MP4 can't hold). 1080p and below save as `.mp4`.
- MP3s are 320 kbps. Change `mp3_kbps` in `core.py` if you want smaller files.
- If downloads suddenly break: rebuild (Actions → Run workflow) to get the latest yt-dlp.
- Downloading is against YouTube's Terms of Service except where the uploader allows it. Use it for your own content, Creative Commons videos, or material you have rights to.
