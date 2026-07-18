from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import mss

from .vectorize import vectorize_image
from .i18n import tr


class VectorizeDialog(tk.Toplevel):
    MODES = (
        ("color", "フルカラーSVG", "色と陰影をパス化。見た目重視でファイルは大きめです。"),
        ("outline", "輪郭線SVG", "外形と画像内の主要な境界線を線として出力します。"),
        ("silhouette", "シルエットSVG＋DXF", "透明部分との境界を外周線・塗り形状として出力します。"),
    )

    def __init__(self, parent: tk.Misc, source: Path):
        super().__init__(parent)
        self.source = source
        self.processing = False
        self.ui_events: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._ui_poll_id: str | None = None
        self.mode_var = tk.StringVar(value="color")
        self.dxf_internal_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=tr("対象: {name}", name=source.name))
        self.title(tr("ベクター化"))
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="出力方式を選択してください", font=("", 12, "bold")).grid(
            row=0, column=0, sticky="ew", padx=18, pady=(18, 10)
        )
        modes = ttk.Frame(self)
        modes.grid(row=1, column=0, sticky="nsew", padx=18)
        modes.columnconfigure(0, weight=1)
        self.description_labels: list[ttk.Label] = []
        for value, title, description in self.MODES:
            frame = ttk.Frame(modes)
            frame.pack(fill="x", pady=6)
            ttk.Radiobutton(frame, text=title, variable=self.mode_var, value=value,
                            command=self._mode_changed).pack(anchor="w")
            description_label = ttk.Label(
                frame, text=description, foreground="#555555", justify="left", wraplength=680,
            )
            description_label.pack(fill="x", anchor="w", padx=(24, 0), pady=(2, 0))
            self.description_labels.append(description_label)
        self.internal_check = ttk.Checkbutton(
            self, text="DXFに目・口・髪・服などの内部線も出力", variable=self.dxf_internal_var,
            state="disabled",
        )
        self.internal_check.grid(row=2, column=0, sticky="w", padx=42, pady=(4, 6))
        ttk.Separator(self).grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 0))
        self.status_label = ttk.Label(self, textvariable=self.status_var, wraplength=700)
        self.status_label.grid(
            row=4, column=0, sticky="ew", padx=18, pady=(10, 4)
        )
        buttons = ttk.Frame(self)
        buttons.grid(row=5, column=0, sticky="ew", padx=18, pady=(8, 16))
        self.close_button = ttk.Button(buttons, text="閉じる", command=self._close)
        self.close_button.pack(side="right", padx=4)
        self.export_button = ttk.Button(buttons, text="ベクター化して保存", command=self._export)
        self.export_button.pack(side="right", padx=4)
        self._set_initial_geometry(parent)
        self.bind("<Configure>", self._window_resized, add="+")
        self._ui_poll_id = self.after(100, self._poll_ui_events)

    def _set_initial_geometry(self, parent: tk.Misc) -> None:
        """Size the dialog for the application's DPI while keeping it on screen."""
        self.update_idletasks()
        scale = max(1.0, min(2.5, float(getattr(parent, "ui_scale", 1.0))))
        parent.update_idletasks()
        parent_left, parent_top = parent.winfo_rootx(), parent.winfo_rooty()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        center_x = parent_left + parent_width // 2
        center_y = parent_top + parent_height // 2
        monitor_left, monitor_top = 0, 0
        monitor_width = max(640, self.winfo_screenwidth())
        monitor_height = max(480, self.winfo_screenheight())
        try:
            with mss.mss() as grabber:
                monitors = [dict(item) for item in grabber.monitors[1:]]
            monitor = next(
                item for item in monitors
                if item["left"] <= center_x < item["left"] + item["width"]
                and item["top"] <= center_y < item["top"] + item["height"]
            )
            monitor_left, monitor_top = monitor["left"], monitor["top"]
            monitor_width, monitor_height = monitor["width"], monitor["height"]
        except Exception:
            logging.debug("Could not determine the vector dialog monitor", exc_info=True)
            pass

        width = min(max(round(760 * scale), self.winfo_reqwidth()), monitor_width - 40)
        height = min(max(round(500 * scale), self.winfo_reqheight()), monitor_height - 80)
        left = center_x - width // 2
        top = center_y - height // 2
        left = max(monitor_left + 20, min(left, monitor_left + monitor_width - width - 20))
        top = max(monitor_top + 20, min(top, monitor_top + monitor_height - height - 40))
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(min(width, max(600, round(620 * scale))),
                     min(height, max(400, round(440 * scale))))
        self.resizable(True, True)

    def _window_resized(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        wraplength = max(280, event.width - 84)
        for label in self.description_labels:
            label.configure(wraplength=wraplength)
        self.status_label.configure(wraplength=max(280, event.width - 40))

    def _mode_changed(self) -> None:
        self.internal_check.configure(state="normal" if self.mode_var.get() == "silhouette" else "disabled")

    def _export(self) -> None:
        if self.processing:
            return
        self.processing = True
        self.export_button.configure(state="disabled")
        self.close_button.configure(state="disabled")
        self.status_var.set(tr("ベクター化しています…"))
        mode = self.mode_var.get()
        internal_lines = self.dxf_internal_var.get()

        def worker() -> None:
            try:
                outputs = vectorize_image(self.source, mode, dxf_internal_lines=internal_lines)
                self.ui_events.put(("completed", outputs))
            except Exception as exc:
                logging.exception("vector dialog export failed")
                self.ui_events.put(("failed", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_ui_events(self) -> None:
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                if kind == "completed":
                    self._completed(list(value))
                elif kind == "failed":
                    self._failed(str(value))
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self._ui_poll_id = self.after(100, self._poll_ui_events)
        except tk.TclError:
            self._ui_poll_id = None

    def _completed(self, outputs: list[Path]) -> None:
        self.processing = False
        self.export_button.configure(state="normal")
        self.close_button.configure(state="normal")
        self.status_var.set(tr("出力完了: {names}", names=", ".join(path.name for path in outputs)))
        if messagebox.askyesno("ベクター化完了", "出力しました。保存フォルダを開きますか？\n\n" + "\n".join(map(str, outputs)), parent=self):
            os.startfile(outputs[0].parent)

    def _failed(self, error: str) -> None:
        self.processing = False
        self.export_button.configure(state="normal")
        self.close_button.configure(state="normal")
        self.status_var.set(tr("ベクター化に失敗しました"))
        messagebox.showerror("ベクター化エラー", error, parent=self)

    def _close(self) -> None:
        if self.processing:
            self.status_var.set(tr("ベクター化の完了を待っています…"))
            return
        if self._ui_poll_id:
            self.after_cancel(self._ui_poll_id)
            self._ui_poll_id = None
        self.grab_release()
        self.destroy()
