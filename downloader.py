import subprocess
import threading
import re
import os
import sys
import shutil
import signal
import shlex
import urllib.request
from urllib.parse import urlparse

IS_WIN = sys.platform == "win32"

YOUTUBE_HOST_HINTS  = ("youtube.com", "youtu.be", "music.youtube.com")
YTDLP_GUI_BIN_DIR   = os.path.join(os.path.expanduser("~"), ".yt-dlp-gui", "bin")
YTDLP_OVERRIDE_PATH = os.path.join(YTDLP_GUI_BIN_DIR, "yt-dlp.exe")
YTDLP_LATEST_URL    = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

PROGRESS_TEMPLATE = (
    "%(progress.status)s__SEP__"
    "%(progress._total_bytes_estimate_str)s__SEP__"
    "%(progress._percent_str)s__SEP__"
    "%(progress._speed_str)s__SEP__"
    "%(progress._eta_str)s__SEP__"
    "%(info.title)s"
)

PRESETS = {
    "best": "-f bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
    "mp4":  "-f bv*[vcodec^=avc]+ba[ext=m4a]/b",
    "mp3":  "--extract-audio --audio-format mp3 --audio-quality 0",
}
DEFAULT_FORMAT = PRESETS["best"]


# helpers

def get_base_path() -> str:
    """Returns _MEIPASS when bundled with PyInstaller, otherwise the script directory."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.abspath(os.path.dirname(__file__))


def find_ytdlp() -> str:
    """Locate the yt-dlp binary. Priority: user override -> bundled -> PATH -> common paths."""
    binary = "yt-dlp.exe" if IS_WIN else "yt-dlp"
    base   = get_base_path()

    if IS_WIN and os.path.isfile(YTDLP_OVERRIDE_PATH):
        return YTDLP_OVERRIDE_PATH

    bundled = os.path.join(base, binary)
    if os.path.isfile(bundled):
        return bundled

    found = shutil.which(binary)
    if found:
        return found

    if IS_WIN:
        for p in [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "yt-dlp", "yt-dlp.exe"),
            os.path.join(os.environ.get("USERPROFILE",  ""), "Downloads", "yt-dlp.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "yt-dlp", "yt-dlp.exe"),
        ]:
            if p and os.path.isfile(p):
                return p

    return binary


def find_ffmpeg() -> str:
    """Locate the ffmpeg binary."""
    binary  = "ffmpeg.exe" if IS_WIN else "ffmpeg"
    base    = get_base_path()
    bundled = os.path.join(base, binary)
    if os.path.isfile(bundled):
        return bundled
    found = shutil.which(binary)
    if found:
        return found
    if IS_WIN:
        for p in [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        ]:
            if p and os.path.isfile(p):
                return p
    return binary


def _popen_kwargs() -> dict:
    """Platform-specific kwargs for subprocess.Popen."""
    kw = {}
    if IS_WIN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["preexec_fn"] = os.setsid
    return kw


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(hint in host for hint in YOUTUBE_HOST_HINTS)


# downloader

class Downloader:
    """Manages the yt-dlp subprocess."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir  = output_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.process     = None
        self.cancelled   = False
        self.ytdlp_path  = find_ytdlp()
        self.ffmpeg_path = find_ffmpeg()

    def _build_cmd(
        self,
        url: str,
        format_str: str,
        cookies_file: str | None,
        cookies_browser: str | None,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Build a minimal yt-dlp command — no custom headers or user-agents."""
        yt = self.ytdlp_path
        ff = self.ffmpeg_path

        cmd = [
            yt,
            "--newline",
            "--no-simulate",
            "--progress",
            "--progress-template", PROGRESS_TEMPLATE,
            "--merge-output-format", "mp4",
            "-P", self.output_dir,
            "-o", "%(title)s.%(ext)s",
        ]

        if ff and ff != "ffmpeg":
            cmd += ["--ffmpeg-location", ff]

        if cookies_file:
            cmd += ["--cookies", cookies_file]
        elif cookies_browser:
            cmd += ["--cookies-from-browser", cookies_browser]

        cmd += shlex.split(format_str)

        if extra_args:
            cmd += extra_args

        cmd += ["--", url]
        return cmd

    def _build_strategies(
        self,
        url: str,
        format_str: str,
        cookies_file: str | None,
        cookies_browser: str | None,
    ) -> list[tuple[str, list[str]]]:
        """Return ordered list of download strategies to try.

        1. default — yt-dlp own choice (best quality)
        2. youtube android — no JS runtime / PO token needed
        3. youtube ios — alternative client
        4. youtube android, no cookies — last resort
        """
        strategies: list[tuple[str, list[str]]] = []

        strategies.append((
            "default",
            self._build_cmd(url, format_str, cookies_file, cookies_browser),
        ))

        if _is_youtube_url(url):
            strategies.append((
                "youtube android",
                self._build_cmd(
                    url, format_str, cookies_file, cookies_browser,
                    extra_args=["--extractor-args", "youtube:player_client=android"],
                ),
            ))

            strategies.append((
                "youtube ios",
                self._build_cmd(
                    url, format_str, cookies_file, cookies_browser,
                    extra_args=["--extractor-args", "youtube:player_client=ios"],
                ),
            ))

            strategies.append((
                "youtube android no-cookies",
                self._build_cmd(
                    url, format_str, None, None,
                    extra_args=["--extractor-args", "youtube:player_client=android"],
                ),
            ))

        return strategies

    def _run_attempt(
        self, cmd: list[str], on_progress
    ) -> tuple[bool, bool, bool, bool]:
        """Run a single strategy attempt.

        Returns:
            (ok, had_signature_issue, only_images_available, needs_signin)
        """
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **_popen_kwargs(),
        )

        had_signature_issue   = False
        only_images_available = False
        needs_signin          = False

        for line in self.process.stdout:
            if self.cancelled:
                self.process.kill()
                return (False, had_signature_issue, only_images_available, needs_signin)

            line = line.rstrip()
            if on_progress:
                on_progress(line)

            lowered = line.lower()
            if "signature solving failed" in lowered or "n challenge solving failed" in lowered:
                had_signature_issue = True
            if "only images are available" in lowered:
                only_images_available = True
            if "sign in to confirm" in lowered or "confirm you're not a bot" in lowered:
                needs_signin = True

        self.process.wait()
        return (
            self.process.returncode == 0,
            had_signature_issue,
            only_images_available,
            needs_signin,
        )

    def _auto_update_ytdlp_windows(self, on_progress=None) -> bool:
        """Download the latest yt-dlp.exe to the persistent override directory."""
        if not IS_WIN:
            return False
        try:
            os.makedirs(YTDLP_GUI_BIN_DIR, exist_ok=True)
            temp_path = YTDLP_OVERRIDE_PATH + ".tmp"
            if on_progress:
                on_progress("[info] auto-updating yt-dlp to fix YouTube challenge...")
            urllib.request.urlretrieve(YTDLP_LATEST_URL, temp_path)
            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) < 1_000_000:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                if on_progress:
                    on_progress("[warn] yt-dlp update file looks invalid, skipping")
                return False
            if os.path.exists(YTDLP_OVERRIDE_PATH):
                os.remove(YTDLP_OVERRIDE_PATH)
            os.replace(temp_path, YTDLP_OVERRIDE_PATH)
            self.ytdlp_path = YTDLP_OVERRIDE_PATH
            if on_progress:
                on_progress(f"[info] yt-dlp updated: {self.ytdlp_path}")
            return True
        except Exception as e:
            if on_progress:
                on_progress(f"[warn] yt-dlp auto-update failed: {e}")
            return False

    def download(
        self,
        url: str,
        on_progress=None,
        on_finished=None,
        on_error=None,
        cookies_file: str | None = None,
        cookies_browser: str | None = None,
        format_str: str = DEFAULT_FORMAT,
    ):
        """Start the download in a background thread."""
        self.cancelled = False

        def _run():
            try:
                had_signature_issue_any = False
                only_images_any         = False
                needs_signin_any        = False
                auto_update_tried       = False

                while True:
                    strategies = self._build_strategies(
                        url, format_str, cookies_file, cookies_browser
                    )

                    had_sig_round      = False
                    only_img_round     = False
                    needs_signin_round = False

                    for i, (label, cmd) in enumerate(strategies):
                        if self.cancelled:
                            return

                        if i > 0 and on_progress:
                            on_progress(f"[retry {i}/{len(strategies)-1}] trying {label}...")

                        ok, had_sig, only_img, needs_signin = self._run_attempt(
                            cmd, on_progress
                        )
                        had_sig_round      = had_sig_round      or had_sig
                        only_img_round     = only_img_round     or only_img
                        needs_signin_round = needs_signin_round or needs_signin

                        if ok:
                            if on_finished and not self.cancelled:
                                on_finished()
                            return

                        if self.cancelled:
                            return

                    had_signature_issue_any = had_signature_issue_any or had_sig_round
                    only_images_any         = only_images_any         or only_img_round
                    needs_signin_any        = needs_signin_any        or needs_signin_round

                    # auto-update yt-dlp once when a signature challenge is hit;
                    # skip if sign-in is required since updating won't help
                    if (
                        _is_youtube_url(url)
                        and (had_sig_round or only_img_round)
                        and not needs_signin_round
                        and not auto_update_tried
                    ):
                        auto_update_tried = True
                        if self._auto_update_ytdlp_windows(on_progress=on_progress):
                            if on_progress:
                                on_progress("[info] retrying with updated yt-dlp...")
                            continue

                    break

                if not self.cancelled and on_error:
                    if needs_signin_any:
                        on_error(
                            "YouTube requires sign-in (bot check / age restriction).\n"
                            "Fix: log in to YouTube in your browser, export cookies.txt "
                            "with 'Get cookies.txt LOCALLY', then select it in manual mode."
                        )
                    elif had_signature_issue_any or only_images_any:
                        on_error(
                            "YouTube download failed.\n"
                            "Try:\n"
                            "1) Use cookies: log in to YouTube, export cookies.txt with "
                            "'Get cookies.txt LOCALLY'.\n"
                            "2) Install Node.js: nodejs.org"
                        )
                    else:
                        on_error("All download strategies failed.")

            except FileNotFoundError:
                if on_error:
                    on_error("yt-dlp not found. Please install it first.")
            except Exception as e:
                if on_error:
                    on_error(str(e))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    def cancel(self):
        """Cancel the current download."""
        self.cancelled = True
        if self.process:
            try:
                if IS_WIN:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass

    @staticmethod
    def parse_progress(line: str) -> dict | None:
        """Parse a __SEP__-delimited progress line.

        Returns:
            dict with keys: status, total, percent, speed, eta, title — or None.
        """
        if "__SEP__" not in line:
            return None
        parts = [p.strip() for p in line.split("__SEP__")]
        if len(parts) < 6:
            return None
        return {
            "status":  parts[0],
            "total":   parts[1],
            "percent": parts[2],
            "speed":   parts[3],
            "eta":     parts[4],
            "title":   parts[5],
        }

    @staticmethod
    def parse_percent(line: str) -> float | None:
        """Extract the percentage value from a progress line."""
        if "__SEP__" in line:
            parts = line.split("__SEP__")
            if len(parts) >= 3:
                try:
                    return float(parts[2].strip().replace("%", ""))
                except ValueError:
                    pass
        m = re.search(r"(\d+\.?\d*)%", line)
        return float(m.group(1)) if m else None
