import subprocess
import threading
import re
import os
import json


DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
DEFAULT_REFERER = "https://www.google.com/"


class Downloader:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.process = None
        self.cancelled = False

    def build_command(self, url, format_str="bv*+ba/b", cookies_browser="firefox",
                      use_hls_fallback=False, extra_args=None):
        cmd = ["yt-dlp"]

        if use_hls_fallback:
            cmd += ["-f", "best[protocol=m3u8]/best"]
        else:
            cmd += ["-f", format_str]

        if cookies_browser:
            cmd += ["--cookies-from-browser", cookies_browser]

        cmd += [
            "--user-agent", DEFAULT_USER_AGENT,
            "--referer", DEFAULT_REFERER,
            "--geo-bypass",
            "--no-check-certificate",
            "--merge-output-format", "mp4",
            "--newline",
            "-o", os.path.join(self.output_dir, "%(title)s.%(ext)s"),
        ]

        if extra_args:
            cmd += extra_args

        cmd.append(url)
        return cmd

    def get_video_info(self, url, cookies_browser="firefox"):
        cmd = [
            "yt-dlp", "--dump-json", "--no-download",
            "--no-check-certificate", "--geo-bypass",
        ]
        if cookies_browser:
            cmd += ["--cookies-from-browser", cookies_browser]
        cmd += [
            "--user-agent", DEFAULT_USER_AGENT,
            "--referer", DEFAULT_REFERER,
            url,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def download(self, url, on_progress=None, on_finished=None, on_error=None,
                 cookies_browser="firefox", format_str="bv*+ba/b"):
        self.cancelled = False

        def _run():
            cmd = self.build_command(url, format_str=format_str, cookies_browser=cookies_browser)
            try:
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )

                got_404 = False
                output_lines = []

                for line in self.process.stdout:
                    if self.cancelled:
                        self.process.kill()
                        return

                    line = line.strip()
                    output_lines.append(line)

                    if on_progress:
                        on_progress(line)

                    if "HTTP Error 404" in line or "HTTP Error 412" in line:
                        got_404 = True

                self.process.wait()

                # 404/412 retry with hls
                if got_404 and not self.cancelled:
                    if on_progress:
                        on_progress("[retry] switching to hls format...")

                    cmd = self.build_command(url, cookies_browser=cookies_browser, use_hls_fallback=True)
                    self.process = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1
                    )

                    for line in self.process.stdout:
                        if self.cancelled:
                            self.process.kill()
                            return
                        line = line.strip()
                        if on_progress:
                            on_progress(line)

                    self.process.wait()

                    if self.process.returncode != 0 and on_error:
                        on_error("download failed even with hls fallback")
                    elif on_finished and not self.cancelled:
                        on_finished()
                elif self.process.returncode != 0 and not self.cancelled:
                    if on_error:
                        on_error("download failed (exit code {})".format(self.process.returncode))
                elif not self.cancelled:
                    if on_finished:
                        on_finished()

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
        # tries to pull percentage from yt-dlp output
        match = re.search(r'(\d+\.?\d*)%', line)
        if match:
            return float(match.group(1))
        return None
