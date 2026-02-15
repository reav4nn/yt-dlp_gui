import subprocess
import threading
import re
import os
import sys
import json
import shutil
from urllib.parse import urlparse


DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Mode": "navigate",
}

IS_WIN = sys.platform == "win32"


def find_ytdlp():
    # check PATH first
    found = shutil.which("yt-dlp")
    if found:
        return found

    if not IS_WIN:
        return "yt-dlp"

    # common windows locations
    spots = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "yt-dlp.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "yt-dlp", "yt-dlp.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "yt-dlp", "yt-dlp.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Downloads", "yt-dlp.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "yt-dlp", "yt-dlp.exe"),
        "C:\\yt-dlp\\yt-dlp.exe",
    ]
    for p in spots:
        if p and os.path.isfile(p):
            return p

    return "yt-dlp"


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found

    if not IS_WIN:
        return "ffmpeg"

    spots = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
    ]
    for p in spots:
        if p and os.path.isfile(p):
            return p

    return "ffmpeg"


def _popen_kwargs():
    # hide console window on windows
    kw = {}
    if IS_WIN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
    return kw


def _referer_for_url(url):
    parsed = urlparse(url)
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}/"
    return "https://www.google.com/"


def _origin_for_url(url):
    parsed = urlparse(url)
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}"
    return None


class Downloader:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.process = None
        self.cancelled = False
        self.ytdlp_path = find_ytdlp()
        self.ffmpeg_path = find_ffmpeg()

    def _base_args(self, url, cookies_browser):
        # stuff that goes into every command
        cmd = []
        if cookies_browser:
            cmd += ["--cookies-from-browser", cookies_browser]

        referer = _referer_for_url(url)
        origin = _origin_for_url(url)

        cmd += [
            "--user-agent", DEFAULT_USER_AGENT,
            "--referer", referer,
            "--geo-bypass",
            "--no-check-certificate",
            "--merge-output-format", "mp4",
            "--newline",
            "-o", os.path.join(self.output_dir, "%(title)s.%(ext)s"),
        ]

        for k, v in BROWSER_HEADERS.items():
            cmd += ["--add-header", f"{k}:{v}"]

        if origin:
            cmd += ["--add-header", f"Origin:{origin}"]

        return cmd

    def _build_strategies(self, url, format_str, cookies_browser):
        yt = self.ytdlp_path
        ff = self.ffmpeg_path
        strategies = []

        # 1: normal
        cmd = [yt, "-f", format_str]
        cmd += self._base_args(url, cookies_browser)
        if ff != "ffmpeg":
            cmd += ["--ffmpeg-location", ff]
        cmd.append(url)
        strategies.append(("default", cmd))

        # 2: hls fallback + legacy server connect
        cmd = [yt, "-f", "best[protocol=m3u8]/best"]
        cmd += self._base_args(url, cookies_browser)
        cmd += ["--legacy-server-connect"]
        if ff != "ffmpeg":
            cmd += ["--ffmpeg-location", ff]
        cmd.append(url)
        strategies.append(("hls + legacy-server-connect", cmd))

        # 3: ffmpeg external downloader + legacy
        cmd = [yt, "-f", format_str]
        cmd += self._base_args(url, cookies_browser)
        cmd += [
            "--legacy-server-connect",
            "--downloader", ff,
            "--downloader-args", "ffmpeg:-headers 'User-Agent: " + DEFAULT_USER_AGENT + "'",
        ]
        if ff != "ffmpeg":
            cmd += ["--ffmpeg-location", ff]
        cmd.append(url)
        strategies.append(("ffmpeg downloader", cmd))

        # 4: nuclear - hls + ffmpeg + sleep between requests
        cmd = [yt, "-f", "best[protocol=m3u8]/best"]
        cmd += self._base_args(url, cookies_browser)
        cmd += [
            "--legacy-server-connect",
            "--downloader", ff,
            "--sleep-requests", "1",
            "--extractor-retries", "3",
        ]
        if ff != "ffmpeg":
            cmd += ["--ffmpeg-location", ff]
        cmd.append(url)
        strategies.append(("hls + ffmpeg + throttle", cmd))

        return strategies

    def get_video_info(self, url, cookies_browser="firefox"):
        cmd = [self.ytdlp_path, "--dump-json", "--no-download"]
        cmd += self._base_args(url, cookies_browser)
        cmd += ["--legacy-server-connect"]
        cmd.append(url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, **_popen_kwargs())
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def _run_attempt(self, cmd, on_progress):
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, **_popen_kwargs()
        )

        had_http_error = False
        had_cookie_error = False

        for line in self.process.stdout:
            if self.cancelled:
                self.process.kill()
                return (False, False, False)

            line = line.strip()
            if on_progress:
                on_progress(line)

            if "HTTP Error 404" in line or "HTTP Error 412" in line:
                had_http_error = True
            ll = line.lower()
            if ("could not copy" in ll and "cookie" in ll) or "failed to decrypt" in ll:
                had_cookie_error = True

        self.process.wait()
        ok = self.process.returncode == 0
        return (ok, had_http_error, had_cookie_error)

    def download(self, url, on_progress=None, on_finished=None, on_error=None,
                 cookies_browser="firefox", format_str="bv*+ba/b"):
        self.cancelled = False

        def _run():
            try:
                strategies = self._build_strategies(url, format_str, cookies_browser)

                for i, (label, cmd) in enumerate(strategies):
                    if self.cancelled:
                        return

                    if i > 0 and on_progress:
                        on_progress(f"[retry {i}/{len(strategies)-1}] trying: {label}...")

                    ok, had_http_error, had_cookie_error = self._run_attempt(cmd, on_progress)

                    if ok:
                        if on_finished and not self.cancelled:
                            on_finished()
                        return

                    if self.cancelled:
                        return

                    if had_cookie_error:
                        # browser is locking the cookie db, retrying with same browser is pointless
                        if on_progress:
                            on_progress("[warn] browser is locking cookies, retrying without cookies...")
                            on_progress("[warn] close the browser for cookie access, or this will try without them")

                        # rebuild strategies without cookies and run them
                        no_cookie_strategies = self._build_strategies(url, format_str, None)
                        for j, (nc_label, nc_cmd) in enumerate(no_cookie_strategies):
                            if self.cancelled:
                                return
                            if j > 0 and on_progress:
                                on_progress(f"[retry {j}/{len(no_cookie_strategies)-1}] (no cookies) {nc_label}...")

                            nc_ok, _, _ = self._run_attempt(nc_cmd, on_progress)
                            if nc_ok:
                                if on_finished and not self.cancelled:
                                    on_finished()
                                return

                        if not self.cancelled and on_error:
                            on_error("failed. close the browser and try again for cookie access")
                        return

                    if not had_http_error and i == 0:
                        continue

                if not self.cancelled and on_error:
                    on_error("all download strategies failed")

            except FileNotFoundError:
                if on_error:
                    on_error("yt-dlp not found. install it first")
            except Exception as e:
                if on_error:
                    on_error(str(e))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    def cancel(self):
        self.cancelled = True
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass

    @staticmethod
    def parse_progress(line):
        match = re.search(r'(\d+\.?\d*)%', line)
        if match:
            return float(match.group(1))
        return None
