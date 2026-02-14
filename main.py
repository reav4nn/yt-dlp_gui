import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading
import os
import re

from downloader import Downloader


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("yt-dlp gui")
        self.geometry("780x560")
        self.minsize(650, 480)

        self.downloader = Downloader()
        self.downloading = False

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # url section
        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        url_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(url_frame, text="url", font=("", 14, "bold")).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="paste video link here...", height=36)
        self.url_entry.grid(row=0, column=1, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self._start_download())

        # settings row
        settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        settings_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(settings_frame, text="browser cookies").pack(side="left", padx=(0, 6))
        self.browser_var = ctk.StringVar(value="firefox")
        self.browser_menu = ctk.CTkOptionMenu(
            settings_frame, variable=self.browser_var,
            values=["firefox", "chrome", "chromium", "brave", "edge", "opera", "none"],
            width=120
        )
        self.browser_menu.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(settings_frame, text="format").pack(side="left", padx=(0, 6))
        self.format_var = ctk.StringVar(value="bv*+ba/b")
        self.format_entry = ctk.CTkEntry(settings_frame, textvariable=self.format_var, width=140)
        self.format_entry.pack(side="left", padx=(0, 16))

        # output dir
        ctk.CTkLabel(settings_frame, text="save to").pack(side="left", padx=(0, 6))
        self.dir_var = ctk.StringVar(value=self.downloader.output_dir)
        self.dir_entry = ctk.CTkEntry(settings_frame, textvariable=self.dir_var, width=180)
        self.dir_entry.pack(side="left", padx=(0, 4))
        ctk.CTkButton(settings_frame, text="...", width=32, command=self._pick_dir).pack(side="left")

        # buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.dl_button = ctk.CTkButton(
            btn_frame, text="download", height=38, font=("", 14, "bold"),
            command=self._start_download
        )
        self.dl_button.pack(side="left", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            btn_frame, text="cancel", height=38, fg_color="#8B0000",
            hover_color="#A52A2A", command=self._cancel_download, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=(0, 16))

        self.progress_bar = ctk.CTkProgressBar(btn_frame, height=14)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.progress_bar.set(0)

        self.pct_label = ctk.CTkLabel(btn_frame, text="0%", width=50)
        self.pct_label.pack(side="left")

        # log area
        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12), state="disabled")
        self.log_box.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="nsew")

        # status bar
        self.status_label = ctk.CTkLabel(self, text="ready", font=("", 11), anchor="w")
        self.status_label.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="ew")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._set_status("enter a url first")
            return

        if self.downloading:
            return

        self.downloading = True
        self.dl_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_bar.set(0)
        self.pct_label.configure(text="0%")

        # clear log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        self.downloader.output_dir = self.dir_var.get()

        cookies = self.browser_var.get()
        if cookies == "none":
            cookies = None

        self._set_status("downloading...")

        self.downloader.download(
            url,
            on_progress=lambda line: self.after(0, self._on_progress, line),
            on_finished=lambda: self.after(0, self._on_finished),
            on_error=lambda err: self.after(0, self._on_error, err),
            cookies_browser=cookies,
            format_str=self.format_var.get(),
        )

    def _on_progress(self, line):
        self._log(line)
        pct = Downloader.parse_progress(line)
        if pct is not None:
            self.progress_bar.set(pct / 100.0)
            self.pct_label.configure(text=f"{pct:.1f}%")
            self._set_status(f"downloading... {pct:.1f}%")

    def _on_finished(self):
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress_bar.set(1.0)
        self.pct_label.configure(text="100%")
        self._set_status("done")
        self._log("-- finished --")

    def _on_error(self, err):
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._set_status(f"error: {err}")
        self._log(f"[error] {err}")

    def _cancel_download(self):
        self.downloader.cancel()
        self.downloading = False
        self.dl_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._set_status("cancelled")
        self._log("-- cancelled --")


if __name__ == "__main__":
    app = App()
    app.mainloop()
