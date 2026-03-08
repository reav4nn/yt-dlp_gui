import subprocess
import threading
import re
import os
import sys
import shutil
import signal
import shlex
import hashlib
import urllib.request
from urllib.parse import urlparse

IS_WIN = sys.platform == "win32"

YOUTUBE_HOST_HINTS  = ("youtube.com", "youtu.be", "music.youtube.com")
YTDLP_GUI_BIN_DIR   = os.path.join(os.path.expanduser("~"), ".yt-dlp-gui", "bin")
YTDLP_OVERRIDE_PATH = os.path.join(YTDLP_GUI_BIN_DIR, "yt-dlp.exe")
YTDLP_LATEST_URL    = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SHA256_URL    = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_SIZE = 64 * 1024

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


def _find_binary(name: str, extra_paths: list[str] | None = None) -> str:
    """Locate a binary from the bundle, PATH, then optional OS-specific paths."""
    binary = f"{name}.exe" if IS_WIN else name
    bundled = os.path.join(get_base_path(), binary)
    if os.path.isfile(bundled):
        return bundled

    found = shutil.which(binary)
    if found:
        return found

    if IS_WIN and extra_paths:
        for path in extra_paths:
            if path and os.path.isfile(path):
                return path

    return binary


def binary_available(path: str | None) -> bool:
    """Return True when a binary path or command name resolves on this machine."""
    if not path:
        return False
    return os.path.isfile(path) or shutil.which(path) is not None


def find_ytdlp() -> str:
    """Locate the yt-dlp binary. Priority: user override -> bundled -> PATH -> common paths."""
    if IS_WIN and os.path.isfile(YTDLP_OVERRIDE_PATH):
        return YTDLP_OVERRIDE_PATH

    return _find_binary(
        "yt-dlp",
        extra_paths=[
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "yt-dlp", "yt-dlp.exe"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Downloads", "yt-dlp.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "yt-dlp", "yt-dlp.exe"),
        ],
    )


def find_ffmpeg() -> str:
    """Locate the ffmpeg binary."""
    return _find_binary(
        "ffmpeg",
        extra_paths=[
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        ],
    )


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
        self._proc_lock  = threading.Lock()

    @staticmethod
    def _insert_extra_args(cmd: list[str], extra_args: list[str] | None) -> list[str]:
        """Insert strategy-specific args before the `-- url` terminator."""
        if not extra_args:
            return list(cmd)

        sentinel_index = cmd.index("--")
        return cmd[:sentinel_index] + extra_args + cmd[sentinel_index:]

    def _build_cmd(
        self,
        url: str,
        format_args: list[str],
        cookies_file: str | None,
        cookies_browser: str | None,
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

        cmd += format_args

        cmd += ["--", url]
        return cmd

    def _build_strategies(
        self,
        url: str,
        format_args: list[str],
        cookies_file: str | None,
        cookies_browser: str | None,
        is_youtube: bool,
    ) -> list[tuple[str, list[str]]]:
        """Return ordered list of download strategies to try.

        1. default — yt-dlp own choice (best quality)
        2. youtube android — no JS runtime / PO token needed
        3. youtube ios — alternative client
        4. youtube android, no cookies — last resort
        """
        base_cmd = self._build_cmd(url, format_args, cookies_file, cookies_browser)
        strategies: list[tuple[str, list[str]]] = [("default", base_cmd)]

        if is_youtube:
            strategies.append((
                "youtube android",
                self._insert_extra_args(
                    base_cmd,
                    ["--extractor-args", "youtube:player_client=android"],
                ),
            ))

            strategies.append((
                "youtube ios",
                self._insert_extra_args(
                    base_cmd,
                    ["--extractor-args", "youtube:player_client=ios"],
                ),
            ))

            no_cookie_cmd = self._build_cmd(url, format_args, None, None)
            strategies.append((
                "youtube android no-cookies",
                self._insert_extra_args(
                    no_cookie_cmd,
                    ["--extractor-args", "youtube:player_client=android"],
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
        with self._proc_lock:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **_popen_kwargs(),
            )

        process = self.process

        had_signature_issue   = False
        only_images_available = False
        needs_signin          = False

        for line in process.stdout:
            if self.cancelled:
                process.kill()
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

        try:
            process.wait()
            return (
                process.returncode == 0,
                had_signature_issue,
                only_images_available,
                needs_signin,
            )
        finally:
            with self._proc_lock:
                if self.process is process:
                    self.process = None

    @staticmethod
    def _calculate_sha256(file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _fetch_expected_sha256(self) -> str | None:
        """Fetch the expected SHA256 for yt-dlp.exe. Returns None on failure."""
        try:
            with urllib.request.urlopen(
                YTDLP_SHA256_URL,
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception:
            return None

        for line in body.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].endswith("yt-dlp.exe"):
                return parts[0].lower()
        return None

    def _download_file(self, url: str, destination: str) -> None:
        """Download a file with a timeout and cancellation checks."""
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with open(destination, "wb") as handle:
                while True:
                    if self.cancelled:
                        raise RuntimeError("cancelled")
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)

    def _auto_update_ytdlp_windows(self, on_progress=None) -> bool:
        """Download the latest yt-dlp.exe to the persistent override directory."""
        if not IS_WIN:
            return False
        temp_path = YTDLP_OVERRIDE_PATH + ".tmp"
        try:
            os.makedirs(YTDLP_GUI_BIN_DIR, exist_ok=True)
            if on_progress:
                on_progress("[info] auto-updating yt-dlp to fix YouTube challenge...")

            expected_sha256 = self._fetch_expected_sha256()
            self._download_file(YTDLP_LATEST_URL, temp_path)

            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) < 1_000_000:
                if on_progress:
                    on_progress("[warn] yt-dlp update file looks invalid, skipping")
                return False

            if expected_sha256:
                actual_sha256 = self._calculate_sha256(temp_path)
                if actual_sha256.lower() != expected_sha256:
                    if on_progress:
                        on_progress("[warn] yt-dlp checksum verification failed, skipping")
                    return False

            if os.path.exists(YTDLP_OVERRIDE_PATH):
                os.remove(YTDLP_OVERRIDE_PATH)
            os.replace(temp_path, YTDLP_OVERRIDE_PATH)
            self.ytdlp_path = YTDLP_OVERRIDE_PATH
            if on_progress:
                on_progress(f"[info] yt-dlp updated: {self.ytdlp_path}")
            return True
        except Exception as e:
            if on_progress and str(e) != "cancelled":
                on_progress(f"[warn] yt-dlp auto-update failed: {e}")
            return False
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

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
                is_youtube              = _is_youtube_url(url)
                format_args             = shlex.split(format_str)

                while True:
                    strategies = self._build_strategies(
                        url, format_args, cookies_file, cookies_browser, is_youtube
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
                        is_youtube
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
        with self._proc_lock:
            process = self.process

        if process:
            try:
                if IS_WIN:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except Exception:
                pass

    @staticmethod
    def parse_progress(line: str) -> dict | None:
        """Parse a __SEP__-delimited progress line.

        Returns:
            dict with keys: status, total, percent, percent_value, speed, eta, title — or None.
        """
        if "__SEP__" not in line:
            return None
        parts = [p.strip() for p in line.split("__SEP__")]
        if len(parts) < 6:
            return None

        try:
            percent_value = float(parts[2].replace("%", ""))
        except ValueError:
            percent_value = None

        return {
            "status":  parts[0],
            "total":   parts[1],
            "percent": parts[2],
            "percent_value": percent_value,
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
