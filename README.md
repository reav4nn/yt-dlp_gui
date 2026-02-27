# yt-dlp GUI — Standalone executables

This project provides a small GUI wrapper for `yt-dlp` designed to be distributed as a
standalone executable (Windows and Linux). Official builds are published as GitHub Releases
so end users can download a single executable with no local Python or dependency setup.

**Important:** Do NOT commit bundled binaries (`yt-dlp`, `ffmpeg`, etc.) to the repository.
Prebuilt executables are available on the Releases page for each tag.

How to get the app

- Visit the repository's Releases page and download the asset matching your OS (Windows `.exe` or Linux binary).
- On Windows: double-click the downloaded `.exe` to run.
- On Linux: make the downloaded file executable (`chmod +x yt-dlp-gui-...-linux`) and run it.

CI / Builds

This project uses GitHub Actions to produce PyInstaller one-file builds for both
Windows and Ubuntu. When a tag like `v1.2.3` is pushed, the workflow downloads
official `yt-dlp` and `ffmpeg` binaries for the current platform, bundles them into
the executable, builds with PyInstaller (`--onefile --noconsole`), and attaches the
artifacts to the created GitHub Release.

Security notes

- The workflow downloads official binary releases over HTTPS at build time; the
  repository does not contain these binaries.
- The application locates bundled binaries at runtime using a secure base path
  (PyInstaller's `_MEIPASS`) when frozen and falls back to PATH if not bundled.

If you are a developer and want to build locally

1. Ensure you have Python 3.10 installed.
2. Create a virtual environment and install dev deps:

```
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt pyinstaller
```

3. Place official `yt-dlp` and `ffmpeg` binaries in a `bin/` folder, then:

```
pyinstaller --noconsole --onefile --name yt-dlp-gui --add-binary "bin/yt-dlp:." --add-binary "bin/ffmpeg:." main.py
```

This will create a standalone executable in `dist/`.

Questions or problems

If you need help or want changes to the build workflow (e.g. other Linux targets,
additional verification of downloaded assets), open an issue and describe the
requested change.
