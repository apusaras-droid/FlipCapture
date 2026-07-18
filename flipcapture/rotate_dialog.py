from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from PIL import Image, ImageOps, ImageTk

from .image_edit import estimate_deskew_angle, line_correction_angle, rotate_image
from .i18n import tr
from .logging_setup import log_event


class RotateDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, source: Path, quality: int,
                 on_saved: Callable[[Path, bool], None]):
        super().__init__(parent)
        self.source = source
        self.quality = quality
        self.on_saved = on_saved
        with Image.open(source) as image:
            self.original = ImageOps.exif_transpose(image).convert("RGBA")
        self.angle = 0.0
        self.preview: ImageTk.PhotoImage | None = None
        self.image_box = (0.0, 0.0, 0.0, 0.0)
        self.manual_mode = False
        self.line_start: tuple[float, float] | None = None
        self.analysis_running = False
        self.analysis_result: tuple[float, int, float, Exception | None] | None = None
        self.title(tr("画像の回転・傾き補正 - {name}", name=source.name))
        self.geometry("840x720")
        self.minsize(680, 540)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_ui()
        self.after_idle(self._render)
        self.grab_set()

    def _build_ui(self) -> None:
        rotate_controls = ttk.Frame(self)
        rotate_controls.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Button(rotate_controls, text="↶ 左へ90°", command=lambda: self._turn(90)).pack(side="left", padx=4)
        ttk.Button(rotate_controls, text="↷ 右へ90°", command=lambda: self._turn(-90)).pack(side="left", padx=4)
        ttk.Button(rotate_controls, text="180°", command=lambda: self._turn(180)).pack(side="left", padx=4)
        ttk.Button(rotate_controls, text="元に戻す", command=self._reset).pack(side="left", padx=12)
        self.angle_var = tk.StringVar(value=tr("回転なし"))
        ttk.Label(rotate_controls, textvariable=self.angle_var).pack(side="right", padx=8)

        deskew_controls = ttk.Frame(self)
        deskew_controls.pack(fill="x", padx=12, pady=(2, 6))
        self.auto_button = ttk.Button(deskew_controls, text="自動で傾きを補正", command=self._auto_deskew)
        self.auto_button.pack(side="left", padx=4)
        self.manual_button = ttk.Button(deskew_controls, text="基準線を手動指定", command=self._start_manual)
        self.manual_button.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(deskew_controls, mode="indeterminate", length=120)
        self.progress.pack(side="left", padx=10)
        self.guide_var = tk.StringVar(value=tr("長い水平線または垂直線を基準に補正できます。"))
        ttk.Label(deskew_controls, textvariable=self.guide_var).pack(side="left", padx=6)

        self.canvas = tk.Canvas(self, background="#242424", cursor="arrow", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=5)
        self.canvas.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<Button-1>", self._manual_click)

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=12)
        self.save_mode_var = tk.StringVar(value="new")
        ttk.Radiobutton(footer, text="別名で保存（_rotated.webp）", variable=self.save_mode_var,
                        value="new").pack(side="left", padx=4)
        ttk.Radiobutton(footer, text="元画像へ上書き", variable=self.save_mode_var,
                        value="overwrite").pack(side="left", padx=12)
        ttk.Button(footer, text="キャンセル", command=self._close).pack(side="right", padx=4)
        ttk.Button(footer, text="補正して保存", command=self._save).pack(side="right", padx=4)

    def _effective_angle(self) -> float:
        value = self.angle % 360.0
        return value if value <= 180 else value - 360

    def _turn(self, amount: float) -> None:
        self.angle = (self.angle + amount) % 360.0
        self.manual_mode = False
        self._render()

    def _reset(self) -> None:
        self.angle = 0.0
        self.manual_mode = False
        self.line_start = None
        self.guide_var.set(tr("長い水平線または垂直線を基準に補正できます。"))
        self._render()

    def _preview_source(self) -> Image.Image:
        image = self.original.copy()
        max_width = max(240, self.canvas.winfo_width() - 24)
        max_height = max(200, self.canvas.winfo_height() - 24)
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        angle = self._effective_angle()
        if abs(angle) >= 0.001:
            rotated = image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            image.close()
            image = rotated
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        return image

    def _render(self) -> None:
        if not self.winfo_exists():
            return
        display = self._preview_source()
        self.preview = ImageTk.PhotoImage(display)
        width, height = display.size
        display.close()
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        left, top = (canvas_width - width) / 2, (canvas_height - height) / 2
        self.image_box = (left, top, left + width, top + height)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width / 2, canvas_height / 2, image=self.preview, anchor="center")
        effective = self._effective_angle()
        self.angle_var.set(tr("回転なし") if abs(effective) < 0.001 else
                           tr("補正角度: {angle:+.2f}°", angle=effective))

    def _auto_deskew(self) -> None:
        if self.analysis_running:
            return
        self.analysis_running = True
        self.manual_mode = False
        self.auto_button.configure(state="disabled")
        self.manual_button.configure(state="disabled")
        self.progress.start(12)
        self.guide_var.set(tr("直線を解析しています…"))
        self.analysis_result = None
        working = self.original.rotate(
            self._effective_angle(), expand=True, resample=Image.Resampling.BICUBIC
        )

        def worker() -> None:
            try:
                correction, lines, confidence = estimate_deskew_angle(working)
                self.analysis_result = (correction, lines, confidence, None)
            except Exception as exc:
                self.analysis_result = (0, 0, 0, exc)
            finally:
                working.close()

        threading.Thread(target=worker, name="deskew-analysis", daemon=True).start()
        self.after(100, self._poll_auto_result)

    def _poll_auto_result(self) -> None:
        if not self.winfo_exists() or not self.analysis_running:
            return
        if self.analysis_result is None:
            self.after(100, self._poll_auto_result)
            return
        self._auto_finished(*self.analysis_result)

    def _auto_finished(self, correction: float, lines: int, confidence: float,
                       error: Exception | None) -> None:
        if not self.winfo_exists():
            return
        self.analysis_running = False
        self.progress.stop()
        self.auto_button.configure(state="normal")
        self.manual_button.configure(state="normal")
        if error is not None:
            logging.warning("automatic deskew failed: %s", error)
            self.guide_var.set(tr("自動検出できませんでした。手動基準線を使用してください。"))
            messagebox.showwarning("自動傾き補正", str(error), parent=self)
            return
        if abs(correction) < 0.05:
            self.guide_var.set(tr("画像はほぼ水平・垂直です。"))
            return
        self.angle = (self.angle + correction) % 360.0
        self.guide_var.set(tr(
            "自動補正 {correction:+.2f}°（検出線 {lines}本 / 信頼度 {confidence:.0%}）",
            correction=correction, lines=lines, confidence=confidence,
        ))
        log_event("deskew_auto_detected", correction=correction, lines=lines, confidence=confidence)
        self._render()

    def _start_manual(self) -> None:
        self.manual_mode = True
        self.line_start = None
        self.canvas.configure(cursor="crosshair")
        self.guide_var.set(tr("画像内の基準にする直線の始点と終点をクリックしてください。"))
        self.canvas.delete("guide")

    def _inside_image(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.image_box
        return left <= x <= right and top <= y <= bottom

    def _manual_click(self, event: tk.Event) -> None:
        if not self.manual_mode or not self._inside_image(event.x, event.y):
            return
        point = (float(event.x), float(event.y))
        if self.line_start is None:
            self.line_start = point
            self.canvas.delete("guide")
            self.canvas.create_oval(event.x - 4, event.y - 4, event.x + 4, event.y + 4,
                                    fill="#00e5ff", outline="white", tags="guide")
            self.guide_var.set(tr("終点をクリックしてください。"))
            return
        x1, y1 = self.line_start
        self.canvas.create_line(x1, y1, event.x, event.y, fill="#00e5ff", width=4, tags="guide")
        try:
            correction = line_correction_angle(x1, y1, event.x, event.y)
        except ValueError as exc:
            self.guide_var.set(str(exc))
            self.line_start = None
            return
        self.angle = (self.angle + correction) % 360.0
        self.manual_mode = False
        self.line_start = None
        self.canvas.configure(cursor="arrow")
        self.guide_var.set(tr("手動基準線で {correction:+.2f}° 補正しました。", correction=correction))
        log_event("deskew_manual_selected", correction=round(correction, 3))
        self.after(350, self._render)

    def _save(self) -> None:
        effective = self._effective_angle()
        if abs(effective) < 0.001:
            messagebox.showwarning("回転角度", "回転または傾き補正を行ってください。", parent=self)
            return
        overwrite = self.save_mode_var.get() == "overwrite"
        if overwrite and not messagebox.askyesno(
            "上書き確認", "元画像を補正後の画像で上書きしますか？", parent=self
        ):
            return
        try:
            path = rotate_image(self.source, effective, overwrite=overwrite, quality=self.quality)
        except Exception as exc:
            messagebox.showerror("回転エラー", str(exc), parent=self)
            return
        self.on_saved(path, overwrite)
        self._close()

    def _close(self) -> None:
        self.original.close()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
