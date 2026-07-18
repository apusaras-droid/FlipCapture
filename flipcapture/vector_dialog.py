from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

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
        self.geometry("650x390")
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        ttk.Label(self, text="出力方式を選択してください", font=("", 12, "bold")).pack(anchor="w", padx=15, pady=(15, 8))
        for value, title, description in self.MODES:
            frame = ttk.Frame(self)
            frame.pack(fill="x", padx=18, pady=5)
            ttk.Radiobutton(frame, text=title, variable=self.mode_var, value=value,
                            command=self._mode_changed).pack(anchor="w")
            ttk.Label(frame, text=description, foreground="#555555").pack(anchor="w", padx=24)
        self.internal_check = ttk.Checkbutton(
            self, text="DXFに目・口・髪・服などの内部線も出力", variable=self.dxf_internal_var,
            state="disabled",
        )
        self.internal_check.pack(anchor="w", padx=42, pady=(2, 4))
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", padx=18, pady=8)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=15, pady=10)
        self.close_button = ttk.Button(buttons, text="閉じる", command=self._close)
        self.close_button.pack(side="right", padx=4)
        self.export_button = ttk.Button(buttons, text="ベクター化して保存", command=self._export)
        self.export_button.pack(side="right", padx=4)
        self._ui_poll_id = self.after(100, self._poll_ui_events)

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
