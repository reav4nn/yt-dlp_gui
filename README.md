# yt-dlp GUI

A simple GUI for [yt-dlp](https://github.com/yt-dlp/yt-dlp) built with CustomTkinter. Supports YouTube and most other sites that yt-dlp can handle.

## features

- **format presets** — best (mp4 + m4a), mp4 (h264), mp3
- **cookies** — manual `cookies.txt`, or read directly from firefox / chrome / edge / opera / opera gx
- **smart youtube fallback** — tries the default yt-dlp client first, then falls back to android and ios clients if that fails (no Node.js or PO token needed for the fallbacks)
- **auto-update** — if a YouTube signature challenge is detected, the app downloads the latest `yt-dlp.exe` once and retries automatically (Windows only)
- **progress display** — shows title, speed, ETA, and file size while downloading

## getting started

### pre-built executable (Windows)

Download the latest release from the Releases page — it's a single `.exe` with everything bundled (yt-dlp, ffmpeg, ffprobe). Just double-click it.

### run from source

You need Python 3.10+ and the dependencies listed in `requirements.txt`.

```bash
git clone <repo-url>
cd yt-dlp_gui
pip install -r requirements.txt
python main.py
```

You also need `yt-dlp` and `ffmpeg` either in your `PATH` or placed in a `bin/` folder next to `main.py`.

## cookie setup

For YouTube videos that require sign-in (age-restricted, etc.):

1. Log in to YouTube in your browser.
2. Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension.
3. Click the extension icon on any YouTube page and export `cookies.txt`.
4. In the app, set the cookie source to **manual** and select the exported file.

Alternatively, pick your browser from the dropdown and the app will read cookies directly from it (the browser must be closed or have cookies unlocked).

## building the executable

Make sure you have `yt-dlp.exe`, `ffmpeg.exe`, and `ffprobe.exe` in a `bin/` folder, then run:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name yt-dlp-gui-windows ^
  --add-binary "bin\yt-dlp.exe;." ^
  --add-binary "bin\ffmpeg.exe;." ^
  --add-binary "bin\ffprobe.exe;." ^
  main.py
```

The output will be in `dist/`.

## notes

- The bundled binaries are **not** committed to the repository. Download them separately from the official yt-dlp and ffmpeg releases before building.
- On first launch the app checks that yt-dlp and ffmpeg are reachable and disables the download button if either is missing.
