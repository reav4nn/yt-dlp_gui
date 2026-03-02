import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading
import os
import sys
import shutil
import re

from downloader import Downloader, find_ytdlp, find_ffmpeg, IS_WIN, DEFAULT_FORMAT, PRESETS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BROWSER_OPTIONS = ["manual", "firefox", "chrome", "edge", "opera", "opera-gx", "none"]
DEFAULT_BROWSER = "manual"

OPERA_GX_WARNING = (
    "Opera GX doesn't allow automatic cookie export, so please use the manual "
    "cookies.txt option instead :)"
)

STARTUP_STATUS = "tip: if you use Opera GX, manual cookies.txt is recommended ❤️"


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("YT-DLP GUI")
        self.geometry("820x600")
        self.minsize(700, 520)

        self.downloader = Downloader()
        self.downloading = False
        self.deps_ok = False
        self.cookies_file_path = None  # path to the manually selected cookies.txt

        self._build_ui()
        self._check_deps()

        if self.deps_ok:
            self._set_status(STARTUP_STATUS)

    # ui setup

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # log area expands with the window

        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        url_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(url_frame, text="URL", font=("", 14, "bold")).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            url_frame, placeholder_text="Paste a video link here...", height=36
        )
        self.url_entry.grid(row=0, column=1, sticky="ew")
        self.url_entry.bind("<Return>", lambda _: self._start_download())

        settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        settings_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(settings_frame, text="cookies").pack(side="left", padx=(0, 6))
        self.browser_var = ctk.StringVar(value=DEFAULT_BROWSER)
        self.browser_menu = ctk.CTkOptionMenu(
            settings_frame,
            variable=self.browser_var,
            values=BROWSER_OPTIONS,
            width=140,
            command=self._on_browser_changed,
        )
        self.browser_menu.pack(side="left", padx=(0, 8))

        self.cookies_btn = ctk.CTkButton(
            settings_frame,
            text="Select cookies.txt",
            width=150,
            command=self._pick_cookies_file,
        )
        self.cookies_btn.pack(side="left", padx=(0, 8))

        self.cookies_file_label = ctk.CTkLabel(
            settings_frame, text="(no file selected)", text_color="gray"
        )
        self.cookies_file_label.pack(side="left", padx=(0, 16))

        # Format
        ctk.CTkLabel(settings_frame, text="format").pack(side="left", padx=(0, 6))
        self.format_var = ctk.StringVar(value="best")
        self.format_menu = ctk.CTkOptionMenu(
            settings_frame,
            variable=self.format_var,
            values=list(PRESETS.keys()),
            width=100,
        )
        self.format_menu.pack(side="left", padx=(0, 16))

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(dir_frame, text="save to").pack(side="left", padx=(0, 6))
        self.dir_var = ctk.StringVar(value=self.downloader.output_dir)
        self.dir_entry = ctk.CTkEntry(dir_frame, textvariable=self.dir_var, width=350)
        self.dir_entry.pack(side="left", padx=(0, 4))
        self.dir_btn = ctk.CTkButton(dir_frame, text="...", width=32, command=self._pick_dir)
        self.dir_btn.pack(side="left")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=16, pady=(0, 4), sticky="ew")

        self.dl_button = ctk.CTkButton(
            btn_frame, text="Download", height=38,
            font=("", 14, "bold"), command=self._start_download,
        )
        self.dl_button.pack(side="left", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            btn_frame, text="Cancel", height=38,
            fg_color="#8B0000", hover_color="#A52A2A",
            command=self._cancel_download, state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(0, 16))

        self.progress_bar = ctk.CTkProgressBar(btn_frame, height=14)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.progress_bar.set(0)

        self.pct_label = ctk.CTkLabel(btn_frame, text="0%", width=50)
        self.pct_label.pack(side="left")

        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12), state="disabled")
        self.log_box.grid(row=4, column=0, padx=16, pady=(0, 4), sticky="nsew")

        self.warning_label = ctk.CTkLabel(
            self,
            text=OPERA_GX_WARNING,
            font=("", 11, "italic"),
            text_color="#00CED1",
            wraplength=750,
            anchor="w",
        )
        self.warning_label.grid(row=5, column=0, padx=16, pady=(2, 2), sticky="ew")

        self.status_label = ctk.CTkLabel(self, text="ready", font=("", 11), anchor="w")
        self.status_label.grid(row=6, column=0, padx=16, pady=(0, 10), sticky="ew")

        self._on_browser_changed(DEFAULT_BROWSER)

    # event handlers

    def _on_browser_changed(self, choice: str):
        """Enable or disable the manual file button depending on the selected cookie mode."""
        if choice == "manual":
            self.cookies_btn.configure(state="normal")
            self.cookies_file_label.configure(
                text=(
                    os.path.basename(self.cookies_file_path)
                    if self.cookies_file_path
                    else "(no file selected)"
                ),
                text_color="gray" if not self.cookies_file_path else "#00FF7F",
            )
        else:
            self.cookies_btn.configure(state="disabled")
            if choice == "opera-gx":
                self.cookies_file_label.configure(
                    text="opera gx (auto)", text_color="#FFD700"
                )
            else:
                self.cookies_file_label.configure(text="", text_color="gray")

    def _pick_cookies_file(self):
        """Open a file dialog to pick a cookies.txt exported by 'Get cookies.txt LOCALLY'."""
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookies_file_path = path
            self.cookies_file_label.configure(
                text=os.path.basename(path), text_color="#00FF7F"
            )
            self._log(f"[info] cookies.txt selected: {path}")

    def _pick_dir(self):
        """Open a dialog to choose the output folder."""
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    # dependency check 

    def _check_deps(self):
        """Check that yt-dlp and ffmpeg are available, and update the UI accordingly."""
        yt = self.downloader.ytdlp_path
        ff = self.downloader.ffmpeg_path

        yt_ok = shutil.which(yt) is not None or os.path.isfile(yt)
        ff_ok = shutil.which(ff) is not None or os.path.isfile(ff)

        msgs = []
        if not yt_ok:
            msgs.append("yt-dlp not found")
        if not ff_ok:
            msgs.append("ffmpeg not found")

        if msgs:
            self.deps_ok = False
            self.dl_button.configure(state="disabled")
            warn = ", ".join(msgs)
            if IS_WIN:
                warn += " — add to PATH or place the .exe next to this program"
            self._set_status(warn)
            self._log(f"[warn] {warn}")
        else:
            self.deps_ok = True
            self.dl_button.configure(state="normal")
            self._set_status(STARTUP_STATUS)

    # cookie logic

    def _resolve_cookie_args(self):
        """Return (cookies_file, cookies_browser) based on the current cookie mode.

        cookies_file    — path for --cookies (manual mode)
        cookies_browser — string for --cookies-from-browser
        """
        sel = self.browser_var.get()

        # manual mode: pass the file directly to --cookies
        if sel == "manual":
            if self.cookies_file_path and os.path.isfile(self.cookies_file_path):
                return (self.cookies_file_path, None)
            else:
                self._log(
                    "[warn] no cookies.txt selected or file not found, continuing without cookies"
                )
                return (None, None)

        # opera gx needs a special profile path argument
        if sel == "opera-gx":
            roaming = os.environ.get("APPDATA", "")
            opera_gx_path = os.path.join(roaming, "Opera Software", "Opera GX Stable")
            if os.path.isdir(opera_gx_path):
                # yt-dlp format: --cookies-from-browser opera:"path"
                browser_arg = f'opera:"{opera_gx_path}"'
                self._log(f"[info] opera gx profile found: {opera_gx_path}")
                return (None, browser_arg)
            else:
                self._log(f"[warn] opera gx profile not found: {opera_gx_path}")
                self._log("[warn] please use manual cookies.txt instead")
                return (None, None)

        # no cookies
        if sel == "none":
            return (None, None)

        # standard browsers — firefox, chrome, edge, opera
        return (None, sel)

    # download control

    def _start_download(self):
        """Validate the URL and kick off the download."""
        if not self.deps_ok:
            return

        url = self.url_entry.get().strip()
        if not url:
            self._set_status("please enter a URL first")
            return

        if not re.match(r"^https?://[^\s]+", url):
            self._set_status("please enter a valid http/https URL")
            return

        if self.downloading:
            return

        self.downloading = True
        self.dl_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._toggle_inputs("disabled")

        self.progress_bar.set(0)
        self.pct_label.configure(text="0%")

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        self.downloader.output_dir = self.dir_var.get()

        cookies_file, cookies_browser = self._resolve_cookie_args()
        self._set_status("downloading...")

        format_str = PRESETS.get(self.format_var.get(), DEFAULT_FORMAT)

        self.downloader.download(
            url,
            on_progress=lambda line: self.after(0, self._on_progress, line),
            on_finished=lambda: self.after(0, self._on_finished),
            on_error=lambda err: self.after(0, self._on_error, err),
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            format_str=format_str,
        )

    # callbacks

    def _on_progress(self, line: str):
        """Called for each output line from yt-dlp."""
        prog = Downloader.parse_progress(line)
        if prog:
            display = (
                f"[{prog['status']}] {prog['title']}  "
                f"{prog['percent']}  {prog['speed']}  ETA {prog['eta']}  ({prog['total']})"
            )
            self._log(display)
        else:
            self._log(line)

        pct = Downloader.parse_percent(line)
        if pct is not None:
            self.progress_bar.set(pct / 100.0)
            self.pct_label.configure(text=f"{pct:.1f}%")
            self._set_status(f"downloading... {pct:.1f}%")

    def _on_finished(self):
        """Called when the download completes successfully."""
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self.progress_bar.set(1.0)
        self.pct_label.configure(text="100%")
        self._set_status("done ✔")
        self._log("── finished ──")

    def _on_error(self, err: str):
        """Called when the download fails."""
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self._set_status(f"error: {err}")
        self._log(f"[error] {err}")

    def _cancel_download(self):
        """Cancel the running download."""
        self.downloader.cancel()
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self._set_status("cancelled")
        self._log("── cancelled ──")

    # helpers

    def _log(self, text: str):
        """Append a line to the log box."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str):
        """Update the status bar text."""
        self.status_label.configure(text=text)

    def _toggle_inputs(self, state: str):
        """Enable or disable all input widgets ('normal' or 'disabled')."""
        self.url_entry.configure(state=state)
        self.browser_menu.configure(state=state)
        self.format_menu.configure(state=state)
        self.dir_entry.configure(state=state)
        self.dir_btn.configure(state=state)
        # the manual cookies button is only active in manual mode
        if state == "normal" and self.browser_var.get() == "manual":
            self.cookies_btn.configure(state="normal")
        else:
            self.cookies_btn.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
