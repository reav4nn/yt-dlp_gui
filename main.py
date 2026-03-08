import customtkinter as ctk
from tkinter import filedialog
import os
import re
import time

from downloader import Downloader, IS_WIN, DEFAULT_FORMAT, PRESETS, binary_available

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BROWSER_OPTIONS = ["manual", "firefox", "chrome", "edge", "opera", "opera-gx", "none"]
DEFAULT_BROWSER = "manual"

LOG_FLUSH_INTERVAL_MS = 150
MAX_LOG_LINES = 2000
PROGRESS_UPDATE_INTERVAL_SECONDS = 0.15
PROGRESS_MIN_DELTA = 0.5

APP_BG = "#050505"
PANEL_BG = "#101010"
FIELD_BG = "#171717"
BORDER = "#2A2A2A"
TEXT = "#F4F4F4"
MUTED = "#A1A1A1"
RED = "#C1121F"
RED_HOVER = "#9B0E19"
RED_DARK = "#2B0A0D"

STATUS_COLORS = {
    "ready": (RED_DARK, "#FF9AA2"),
    "active": ("#2A0D10", "#FF7B85"),
    "warning": ("#332100", "#FFD27A"),
    "error": ("#3A0B10", "#FF9AA2"),
    "success": ("#0E2614", "#8CE6A5"),
}


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("YT-DLP GUI")
        self.geometry("900x720")
        self.minsize(760, 560)
        self.configure(fg_color=APP_BG)

        self.downloader = Downloader()
        self.downloading = False
        self.deps_ok = False
        self.cookies_file_path = None
        self._log_buffer = []
        self._log_flush_scheduled = False
        self._last_progress_value = None
        self._last_progress_update_at = 0.0

        self._init_fonts()
        self._build_ui()
        self._check_deps()

        if self.deps_ok:
            self._set_status("Paste a link and press Start Download.", tone="ready")

    def _init_fonts(self):
        self.title_font = ctk.CTkFont(family="Segoe UI Semibold", size=24, weight="bold")
        self.label_font = ctk.CTkFont(family="Segoe UI", size=13)
        self.value_font = ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold")
        self.log_font = ctk.CTkFont(family="Cascadia Code", size=12)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(
            self,
            fg_color=PANEL_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=18,
        )
        shell.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(5, weight=1)

        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="YT-DLP GUI",
            font=self.title_font,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Simple red and black desktop downloader",
            font=self.label_font,
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.deps_label = ctk.CTkLabel(
            header,
            text="Checking tools",
            font=self.label_font,
            text_color="#FF9AA2",
            fg_color=RED_DARK,
            corner_radius=999,
            padx=12,
            pady=6,
        )
        self.deps_label.grid(row=0, column=1, rowspan=2, sticky="e")

        form = ctk.CTkFrame(shell, fg_color="transparent")
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="URL", font=self.label_font, text_color=MUTED).grid(
            row=0, column=0, sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            form,
            placeholder_text="https://www.youtube.com/watch?v=...",
            height=42,
            fg_color=FIELD_BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text_color=MUTED,
        )
        self.url_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.url_entry.bind("<Return>", lambda _: self._start_download())

        options = ctk.CTkFrame(shell, fg_color="transparent")
        options.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="ew")
        options.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(options, text="Cookies", font=self.label_font, text_color=MUTED).grid(
            row=0, column=0, sticky="w"
        )
        self.browser_var = ctk.StringVar(value=DEFAULT_BROWSER)
        self.browser_menu = ctk.CTkOptionMenu(
            options,
            variable=self.browser_var,
            values=BROWSER_OPTIONS,
            width=150,
            height=38,
            fg_color=RED,
            button_color=RED,
            button_hover_color=RED_HOVER,
            dropdown_fg_color=FIELD_BG,
            dropdown_hover_color=RED_DARK,
            command=self._on_browser_changed,
        )
        self.browser_menu.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.cookies_btn = ctk.CTkButton(
            options,
            text="Choose cookies.txt",
            width=150,
            height=38,
            fg_color=FIELD_BG,
            hover_color=RED_DARK,
            border_width=1,
            border_color=BORDER,
            command=self._pick_cookies_file,
        )
        self.cookies_btn.grid(row=1, column=1, padx=(10, 0), sticky="w", pady=(6, 0))

        ctk.CTkLabel(options, text="Format", font=self.label_font, text_color=MUTED).grid(
            row=0, column=2, sticky="w", padx=(18, 0)
        )
        self.format_var = ctk.StringVar(value="best")
        self.format_menu = ctk.CTkOptionMenu(
            options,
            variable=self.format_var,
            values=list(PRESETS.keys()),
            width=110,
            height=38,
            fg_color=RED,
            button_color=RED,
            button_hover_color=RED_HOVER,
            dropdown_fg_color=FIELD_BG,
            dropdown_hover_color=RED_DARK,
        )
        self.format_menu.grid(row=1, column=2, sticky="w", padx=(18, 0), pady=(6, 0))

        self.dir_var = ctk.StringVar(value=self.downloader.output_dir)
        self.dir_entry = ctk.CTkEntry(
            options,
            textvariable=self.dir_var,
            height=38,
            fg_color=FIELD_BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
        )
        self.dir_entry.grid(row=1, column=3, sticky="ew", padx=(18, 8), pady=(6, 0))

        self.dir_btn = ctk.CTkButton(
            options,
            text="Browse",
            width=88,
            height=38,
            fg_color=FIELD_BG,
            hover_color=RED_DARK,
            border_width=1,
            border_color=BORDER,
            command=self._pick_dir,
        )
        self.dir_btn.grid(row=1, column=4, sticky="e", pady=(6, 0))

        self.cookies_file_label = ctk.CTkLabel(
            shell,
            text="Manual cookies not selected",
            font=self.label_font,
            text_color=MUTED,
            anchor="w",
        )
        self.cookies_file_label.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="ew")

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.grid(row=4, column=0, padx=18, pady=(0, 10), sticky="ew")
        actions.grid_columnconfigure(2, weight=1)

        self.dl_button = ctk.CTkButton(
            actions,
            text="Start Download",
            height=40,
            fg_color=RED,
            hover_color=RED_HOVER,
            font=self.value_font,
            command=self._start_download,
        )
        self.dl_button.grid(row=0, column=0, sticky="w")

        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancel",
            height=40,
            fg_color=FIELD_BG,
            hover_color=RED_DARK,
            border_width=1,
            border_color=BORDER,
            font=self.value_font,
            command=self._cancel_download,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=(10, 0), sticky="w")

        self.pct_label = ctk.CTkLabel(
            actions,
            text="0%",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22, weight="bold"),
            text_color=TEXT,
        )
        self.pct_label.grid(row=0, column=3, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            shell,
            height=14,
            fg_color=FIELD_BG,
            progress_color=RED,
        )
        self.progress_bar.grid(row=5, column=0, padx=18, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            shell,
            text="Ready",
            font=self.label_font,
            text_color="#FF9AA2",
            fg_color=RED_DARK,
            corner_radius=10,
            anchor="w",
            padx=12,
            pady=10,
        )
        self.status_label.grid(row=6, column=0, padx=18, pady=(0, 10), sticky="ew")

        self.log_box = ctk.CTkTextbox(
            shell,
            font=self.log_font,
            state="disabled",
            fg_color="#0C0C0C",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=12,
            wrap="word",
        )
        self.log_box.grid(row=7, column=0, padx=18, pady=(0, 18), sticky="nsew")
        shell.grid_rowconfigure(7, weight=1)

        self._on_browser_changed(DEFAULT_BROWSER)

    def _set_status(self, text: str, tone: str = "ready"):
        fg_color, text_color = STATUS_COLORS.get(tone, STATUS_COLORS["ready"])
        self.status_label.configure(text=text, fg_color=fg_color, text_color=text_color)

    def _set_dependency_state(self, text: str, ok: bool):
        self.deps_label.configure(
            text=text,
            fg_color="#102112" if ok else RED_DARK,
            text_color="#8CE6A5" if ok else "#FF9AA2",
        )

    def _on_browser_changed(self, choice: str):
        if choice == "manual":
            self.cookies_btn.configure(state="normal")
            label_text = os.path.basename(self.cookies_file_path) if self.cookies_file_path else "Manual cookies not selected"
            label_color = TEXT if self.cookies_file_path else MUTED
        elif choice == "none":
            self.cookies_btn.configure(state="disabled")
            label_text = "Cookies disabled"
            label_color = MUTED
        else:
            self.cookies_btn.configure(state="disabled")
            label_text = f"Using {choice.replace('-', ' ').title()} browser session"
            label_color = "#FF9AA2"

        self.cookies_file_label.configure(text=label_text, text_color=label_color)

    def _pick_cookies_file(self):
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookies_file_path = path
            self._on_browser_changed(self.browser_var.get())
            self._log(f"[info] cookies.txt selected: {path}")

    def _pick_dir(self):
        selected_dir = filedialog.askdirectory(initialdir=self.dir_var.get())
        if selected_dir:
            self.dir_var.set(selected_dir)

    def _check_deps(self):
        yt_ok = binary_available(self.downloader.ytdlp_path)
        ff_ok = binary_available(self.downloader.ffmpeg_path)

        missing = []
        if not yt_ok:
            missing.append("yt-dlp")
        if not ff_ok:
            missing.append("ffmpeg")

        if missing:
            self.deps_ok = False
            self.dl_button.configure(state="disabled")
            self._set_dependency_state("Missing tools", ok=False)
            warn = ", ".join(missing) + " not found"
            if IS_WIN:
                warn += ". Add them to PATH or place the executables next to the app."
            self._set_status(warn, tone="warning")
            self._log(f"[warn] {warn}")
        else:
            self.deps_ok = True
            self.dl_button.configure(state="normal")
            self._set_dependency_state("Tools ready", ok=True)
            self._set_status("Paste a link and press Start Download.", tone="ready")

    def _resolve_cookie_args(self):
        selection = self.browser_var.get()

        if selection == "manual":
            if self.cookies_file_path and os.path.isfile(self.cookies_file_path):
                return (self.cookies_file_path, None)
            self._log("[warn] no cookies.txt selected or file not found, continuing without cookies")
            return (None, None)

        if selection == "opera-gx":
            roaming = os.environ.get("APPDATA", "")
            profile_path = os.path.join(roaming, "Opera Software", "Opera GX Stable")
            if os.path.isdir(profile_path):
                return (None, f'opera:"{profile_path}"')
            self._log("[info] selected browser profile was not found, continuing without cookies")
            return (None, None)

        if selection == "none":
            return (None, None)

        return (None, selection)

    def _start_download(self):
        if not self.deps_ok:
            return

        url = self.url_entry.get().strip()
        if not url:
            self._set_status("Enter a URL before starting the download.", tone="warning")
            return

        if not re.match(r"^https?://[^\s]+", url):
            self._set_status("The URL must start with http:// or https://.", tone="warning")
            return

        if self.downloading:
            return

        self.downloading = True
        self.dl_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._toggle_inputs("disabled")

        self.progress_bar.set(0)
        self.pct_label.configure(text="0%")
        self._last_progress_value = None
        self._last_progress_update_at = 0.0
        self._log_buffer.clear()
        self._log_flush_scheduled = False

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        self.downloader.output_dir = self.dir_var.get()
        cookies_file, cookies_browser = self._resolve_cookie_args()
        format_str = PRESETS.get(self.format_var.get(), DEFAULT_FORMAT)

        self._set_status("Download started.", tone="active")

        self.downloader.download(
            url,
            on_progress=lambda line: self.after(0, self._on_progress, line),
            on_finished=lambda: self.after(0, self._on_finished),
            on_error=lambda err: self.after(0, self._on_error, err),
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            format_str=format_str,
        )

    def _on_progress(self, line: str):
        progress = Downloader.parse_progress(line)
        percent = None

        if progress:
            display = (
                f"[{progress['status']}] {progress['title']}  "
                f"{progress['percent']}  {progress['speed']}  ETA {progress['eta']}  ({progress['total']})"
            )
            self._log(display)
            percent = progress["percent_value"]
        else:
            self._log(line)
            percent = Downloader.parse_percent(line)

        if percent is not None and self._should_update_progress(percent):
            self.progress_bar.set(percent / 100.0)
            self.pct_label.configure(text=f"{percent:.1f}%")
            self._set_status(f"Downloading... {percent:.1f}%", tone="active")
            self._last_progress_value = percent
            self._last_progress_update_at = time.monotonic()

    def _on_finished(self):
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self.progress_bar.set(1.0)
        self.pct_label.configure(text="100%")
        self._set_status("Download finished successfully.", tone="success")
        self._log("-- finished --")

    def _on_error(self, err: str):
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self._set_status(err, tone="error")
        self._log(f"[error] {err}")

    def _cancel_download(self):
        self.downloader.cancel()
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._toggle_inputs("normal")
        self._set_status("Download cancelled.", tone="warning")
        self._log("-- cancelled --")

    def _should_update_progress(self, pct: float) -> bool:
        if self._last_progress_value is None:
            return True

        now = time.monotonic()
        if pct >= 100:
            return True
        if abs(pct - self._last_progress_value) >= PROGRESS_MIN_DELTA:
            return True
        return (now - self._last_progress_update_at) >= PROGRESS_UPDATE_INTERVAL_SECONDS

    def _log(self, text: str):
        self._log_buffer.append(text)
        if not self._log_flush_scheduled:
            self._log_flush_scheduled = True
            self.after(LOG_FLUSH_INTERVAL_MS, self._flush_log)

    def _flush_log(self):
        self._log_flush_scheduled = False
        if not self._log_buffer:
            return

        self.log_box.configure(state="normal")
        self.log_box.insert("end", "\n".join(self._log_buffer) + "\n")
        self._log_buffer.clear()

        line_count = int(self.log_box.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            trim_until = line_count - MAX_LOG_LINES
            self.log_box.delete("1.0", f"{trim_until + 1}.0")

        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _toggle_inputs(self, state: str):
        self.url_entry.configure(state=state)
        self.browser_menu.configure(state=state)
        self.format_menu.configure(state=state)
        self.dir_entry.configure(state=state)
        self.dir_btn.configure(state=state)
        if state == "normal" and self.browser_var.get() == "manual":
            self.cookies_btn.configure(state="normal")
        else:
            self.cookies_btn.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()