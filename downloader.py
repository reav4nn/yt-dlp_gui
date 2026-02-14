import subprocess
import threading
import re
import os
import json
from urllib.parse import urlparse


DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Mode": "navigate",
}


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
        # each strategy is (label, cmd list)
        strategies = []

        # 1: normal
        cmd = ["yt-dlp", "-f", format_str]
        cmd += self._base_args(url, cookies_browser)
        cmd.append(url)
        strategies.append(("default", cmd))

        # 2: hls fallback + legacy server connect
        cmd = ["yt-dlp", "-f", "best[protocol=m3u8]/best"]
        cmd += self._base_args(url, cookies_browser)
        cmd += ["--legacy-server-connect"]
        cmd.append(url)
        strategies.append(("hls + legacy-server-connect", cmd))

        # 3: ffmpeg external downloader + legacy
        cmd = ["yt-dlp", "-f", format_str]
        cmd += self._base_args(url, cookies_browser)
        cmd += [
            "--legacy-server-connect",
            "--downloader", "ffmpeg",
            "--downloader-args", "ffmpeg:-headers 'User-Agent: " + DEFAULT_USER_AGENT + "'",
        ]
        cmd.append(url)
        strategies.append(("ffmpeg downloader", cmd))

        # 4: nuclear - hls + ffmpeg + sleep between requests
        cmd = ["yt-dlp", "-f", "best[protocol=m3u8]/best"]
        cmd += self._base_args(url, cookies_browser)
        cmd += [
            "--legacy-server-connect",
            "--downloader", "ffmpeg",
            "--sleep-requests", "1",
            "--extractor-retries", "3",
        ]
        cmd.append(url)
        strategies.append(("hls + ffmpeg + throttle", cmd))

        return strategies

    def get_video_info(self, url, cookies_browser="firefox"):
        cmd = ["yt-dlp", "--dump-json", "--no-download"]
        cmd += self._base_args(url, cookies_browser)
        cmd += ["--legacy-server-connect"]
        cmd.append(url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def _run_attempt(self, cmd, on_progress):
        # runs one strategy, returns (success, had_http_error)
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        had_http_error = False

        for line in self.process.stdout:
            if self.cancelled:
                self.process.kill()
                return (False, False)

            line = line.strip()
            if on_progress:
                on_progress(line)

            if "HTTP Error 404" in line or "HTTP Error 412" in line:
                had_http_error = True

        self.process.wait()
        ok = self.process.returncode == 0
        return (ok, had_http_error)

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

                    ok, had_http_error = self._run_attempt(cmd, on_progress)

                    if ok:
                        if on_finished and not self.cancelled:
                            on_finished()
                        return

                    if self.cancelled:
                        return

                    # no http error means something else went wrong, still try next
                    if not had_http_error and i == 0:
                        # first attempt failed with non-http error, might not be worth retrying
                        # but try once more with legacy connect anyway
                        continue

                # all strategies exhausted
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
