from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

import mss
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

from .background_removal import detect_central_subject, remove_background
from .i18n import tr
from .logging_setup import log_event


def apply_lasso_mask(image: Image.Image, points: list[tuple[int, int]], feather: float = 1.5) -> Image.Image:
    if len(points) < 3:
        raise ValueError("フリーハンド範囲を閉じるには3点以上必要です。")
    result = image.convert("RGBA")
    mask = Image.new("L", result.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    alpha = ImageChops.multiply(result.getchannel("A"), mask)
    result.putalpha(alpha)
    return result


class CropDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, source: Path, quality: int, on_saved: Callable[[Path, bool], None]):
        super().__init__(parent)
        self.withdraw()
        self.source = source
        self.quality = quality
        self.on_saved = on_saved
        self.original = Image.open(source).convert("RGBA")
        self.preview: ImageTk.PhotoImage | None = None
        self.selection_id: int | None = None
        self.lasso_id: int | None = None
        self.lasso_points: list[tuple[float, float]] = []
        self.start: tuple[float, float] | None = None
        self.selection: tuple[float, float, float, float] | None = None
        self.processing = False
        self.cancel_event = threading.Event()
        self.ui_events: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._ui_poll_id: str | None = None
        self.scale = 1.0
        self.offset = (0.0, 0.0)
        self.title(tr("トリミング - {name}", name=source.name))
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_ui()
        self._set_initial_geometry(parent)
        self.deiconify()
        self.after_idle(self._render)
        self._ui_poll_id = self.after(100, self._poll_ui_events)
        self.grab_set()

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 5))
        ttk.Label(header, text="画像上をドラッグして範囲を選択してください。Escで選択解除できます。").pack(side="left")
        self.selection_mode_var = tk.StringVar(value="rectangle")
        ttk.Radiobutton(header, text="矩形", variable=self.selection_mode_var, value="rectangle",
                        command=self._clear_selection).pack(side="right", padx=4)
        ttk.Radiobutton(header, text="フリーハンド", variable=self.selection_mode_var, value="lasso",
                        command=self._clear_selection).pack(side="right", padx=4)
        self.canvas = tk.Canvas(self, background="#242424", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=5)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Configure>", lambda _event: self._render())
        self.bind("<Escape>", lambda _event: self._clear_selection())
        options = ttk.Frame(self)
        options.pack(fill="x", padx=12, pady=(4, 0))
        self.transparent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="選択範囲内の対象だけをAIで切り出し、背景を透過", variable=self.transparent_var,
                        command=self._toggle_ai_options).pack(side="left")
        self.detect_button = ttk.Button(options, text="中央の対象を自動検出", command=self._auto_detect)
        self.detect_button.pack(side="right")

        model_options = ttk.Frame(self)
        model_options.pack(fill="x", padx=12, pady=(4, 0))
        ttk.Label(model_options, text="モデル:").pack(side="left", padx=(0, 4))
        self.model_var = tk.StringVar(value="u2net")
        self.model_combo = ttk.Combobox(model_options, textvariable=self.model_var, state="disabled", width=22,
                                        values=("u2net", "isnet-anime"))
        self.model_combo.pack(side="left")
        ttk.Label(model_options, text="（u2net=汎用 / isnet-anime=イラスト）").pack(side="left", padx=5)

        status = ttk.Frame(self)
        status.pack(fill="x", padx=12, pady=(6, 2))
        self.range_var = tk.StringVar(value=tr("範囲を選択してください"))
        self.range_label = ttk.Label(status, textvariable=self.range_var, anchor="w")
        self.range_label.pack(side="left", fill="x", expand=True)
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=150).pack(side="right", padx=(12, 0))

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(2, 12))
        self.cancel_button = ttk.Button(footer, text="キャンセル", command=self._close)
        self.cancel_button.pack(side="right", padx=4)
        self.new_button = ttk.Button(footer, text="別名で保存（_trim）", command=lambda: self._save(False))
        self.new_button.pack(side="right", padx=4)
        self.overwrite_button = ttk.Button(footer, text="元画像を上書き", command=lambda: self._save(True))
        self.overwrite_button.pack(side="right", padx=4)

    def _set_initial_geometry(self, parent: tk.Misc) -> None:
        """Open at the final DPI-aware size without a smaller intermediate flash."""
        self.update_idletasks()
        scale = max(1.0, min(2.5, float(getattr(parent, "ui_scale", 1.0))))
        parent.update_idletasks()
        parent_left, parent_top = parent.winfo_rootx(), parent.winfo_rooty()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        center_x = parent_left + parent_width // 2
        center_y = parent_top + parent_height // 2
        monitor_left, monitor_top = 0, 0
        monitor_width = max(800, self.winfo_screenwidth())
        monitor_height = max(600, self.winfo_screenheight())
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
            logging.debug("Could not determine the crop dialog monitor", exc_info=True)

        width = min(max(round(1120 * scale), self.winfo_reqwidth()), monitor_width - 40)
        height = min(max(round(800 * scale), self.winfo_reqheight()), monitor_height - 80)
        left = max(
            monitor_left + 20,
            min(center_x - width // 2, monitor_left + monitor_width - width - 20),
        )
        top = max(
            monitor_top + 20,
            min(center_y - height // 2, monitor_top + monitor_height - height - 40),
        )
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(
            min(width, max(760, round(800 * scale))),
            min(height, max(540, round(580 * scale))),
        )
        self.resizable(True, True)

    def _toggle_ai_options(self) -> None:
        self.model_combo.configure(state="readonly" if self.transparent_var.get() else "disabled")

    def _set_model_progress(self, percent: int) -> None:
        self.progress_var.set(percent)
        self.range_var.set(tr("AIモデル準備: {percent}%", percent=percent))

    def _auto_detect(self) -> None:
        if self.processing:
            return
        self.processing = True
        self.cancel_event.clear()
        self.detect_button.configure(state="disabled")
        self.overwrite_button.configure(state="disabled")
        self.new_button.configure(state="disabled")
        self.range_var.set(tr("中央の対象をAIで検出しています…"))
        model = self.model_var.get()

        def worker() -> None:
            try:
                progress = lambda percent: self.ui_events.put(("progress", percent))
                box = detect_central_subject(
                    self.original, model, progress=progress, cancel_event=self.cancel_event
                )
                self.ui_events.put(("detect_succeeded", box))
            except Exception as exc:
                logging.exception("automatic subject detection failed")
                self.ui_events.put(("detect_failed", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_ui_events(self) -> None:
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                if kind == "progress":
                    self._set_model_progress(int(value))
                elif kind == "detect_succeeded":
                    self._auto_detect_succeeded(value)
                elif kind == "detect_failed":
                    self._auto_detect_failed(str(value))
                elif kind == "save_succeeded":
                    destination, overwrite = value
                    self._save_succeeded(destination, overwrite)
                    return
                elif kind == "save_failed":
                    self._save_failed(str(value))
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self._ui_poll_id = self.after(100, self._poll_ui_events)
        except tk.TclError:
            self._ui_poll_id = None

    def _auto_detect_succeeded(self, box: tuple[int, int, int, int]) -> None:
        self.processing = False
        self.progress_var.set(0)
        self.selection_mode_var.set("rectangle")
        self.lasso_points = []
        left, top, right, bottom = box
        x1, y1 = self.offset[0] + left * self.scale, self.offset[1] + top * self.scale
        x2, y2 = self.offset[0] + right * self.scale, self.offset[1] + bottom * self.scale
        self.selection = (x1, y1, x2, y2)
        if self.selection_id:
            self.canvas.delete(self.selection_id)
        self.selection_id = self.canvas.create_rectangle(*self.selection, outline="#00e5ff", width=3)
        self.transparent_var.set(True)
        self._toggle_ai_options()
        self.detect_button.configure(state="normal")
        self.overwrite_button.configure(state="normal")
        self.new_button.configure(state="normal")
        self._update_range()
        log_event("subject_auto_detected", source=str(self.source), crop_box=box, model=self.model_var.get())

    def _auto_detect_failed(self, error: str) -> None:
        self.processing = False
        self.progress_var.set(0)
        self.detect_button.configure(state="normal")
        self.overwrite_button.configure(state="normal")
        self.new_button.configure(state="normal")
        self.range_var.set(tr("対象を自動検出できませんでした"))
        messagebox.showerror("自動検出エラー", error, parent=self)

    def _render(self) -> None:
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        if self.selection or self.lasso_points:
            self.selection = self.start = None
            self.lasso_points = []
            self.range_var.set(tr("画面サイズが変わったため、範囲をもう一度選択してください"))
        self.scale = min(width / self.original.width, height / self.original.height)
        shown_size = (max(1, round(self.original.width * self.scale)), max(1, round(self.original.height * self.scale)))
        shown = self.original.resize(shown_size, Image.Resampling.LANCZOS)
        self.preview = ImageTk.PhotoImage(shown)
        self.offset = ((width - shown_size[0]) / 2, (height - shown_size[1]) / 2)
        self.canvas.delete("all")
        self.canvas.create_image(self.offset[0], self.offset[1], image=self.preview, anchor="nw", tags="image")
        self.selection_id = None
        self.lasso_id = None
        if self.selection:
            self.selection_id = self.canvas.create_rectangle(*self.selection, outline="#00e5ff", width=2)

    def _inside_image(self, x: float, y: float) -> tuple[float, float]:
        left, top = self.offset
        right = left + self.original.width * self.scale
        bottom = top + self.original.height * self.scale
        return max(left, min(right, x)), max(top, min(bottom, y))

    def _press(self, event: tk.Event) -> None:
        self.start = self._inside_image(event.x, event.y)
        if self.selection_mode_var.get() == "lasso":
            self.selection = None
            self.lasso_points = [self.start]
            if self.lasso_id:
                self.canvas.delete(self.lasso_id)
            self.lasso_id = self.canvas.create_line(*self.start, *self.start, fill="#ffca28", width=3,
                                                    smooth=True, splinesteps=12)
            return
        self.lasso_points = []
        self.selection = (*self.start, *self.start)
        if self.selection_id:
            self.canvas.delete(self.selection_id)
        self.selection_id = self.canvas.create_rectangle(*self.selection, outline="#00e5ff", width=2)

    def _drag(self, event: tk.Event) -> None:
        if not self.start:
            return
        end = self._inside_image(event.x, event.y)
        if self.selection_mode_var.get() == "lasso":
            if not self.lasso_id:
                return
            previous = self.lasso_points[-1]
            if abs(end[0] - previous[0]) + abs(end[1] - previous[1]) >= 2:
                self.lasso_points.append(end)
                coordinates = [coordinate for point in self.lasso_points for coordinate in point]
                self.canvas.coords(self.lasso_id, *coordinates)
            self._update_range()
            return
        if not self.selection_id:
            return
        self.selection = (*self.start, *end)
        self.canvas.coords(self.selection_id, *self.selection)
        self._update_range()

    def _release(self, event: tk.Event) -> None:
        self._drag(event)
        if self.selection_mode_var.get() == "lasso" and len(self.lasso_points) >= 3 and self.lasso_id:
            self.lasso_points.append(self.lasso_points[0])
            coordinates = [coordinate for point in self.lasso_points for coordinate in point]
            self.canvas.coords(self.lasso_id, *coordinates)
            self.transparent_var.set(True)
            self._toggle_ai_options()
        self._update_range()

    def _crop_box(self) -> tuple[int, int, int, int] | None:
        if self.selection_mode_var.get() == "lasso":
            if len(self.lasso_points) < 4:
                return None
            xs, ys = zip(*self.lasso_points)
            selection = (min(xs), min(ys), max(xs), max(ys))
        else:
            selection = self.selection
        if not selection:
            return None
        x1, y1, x2, y2 = selection
        left = max(0, round((min(x1, x2) - self.offset[0]) / self.scale))
        top = max(0, round((min(y1, y2) - self.offset[1]) / self.scale))
        right = min(self.original.width, round((max(x1, x2) - self.offset[0]) / self.scale))
        bottom = min(self.original.height, round((max(y1, y2) - self.offset[1]) / self.scale))
        return (left, top, right, bottom) if right - left >= 2 and bottom - top >= 2 else None

    def _update_range(self) -> None:
        box = self._crop_box()
        label = tr("フリーハンド範囲" if self.selection_mode_var.get() == "lasso" else "選択範囲")
        self.range_var.set(
            tr("{label}: {left}, {top} ～ {right}, {bottom}（{width}×{height}）",
               label=label, left=box[0], top=box[1], right=box[2], bottom=box[3],
               width=box[2]-box[0], height=box[3]-box[1])
            if box else tr("有効な範囲を選択してください")
        )

    def _clear_selection(self) -> None:
        self.selection = self.start = None
        self.lasso_points = []
        if self.selection_id:
            self.canvas.delete(self.selection_id)
        self.selection_id = None
        if self.lasso_id:
            self.canvas.delete(self.lasso_id)
        self.lasso_id = None
        self.range_var.set(tr("範囲を選択してください"))

    def _trim_path(self, force_webp: bool = False) -> Path:
        suffix = ".webp" if force_webp else self.source.suffix
        candidate = self.source.with_name(f"{self.source.stem}_trim{suffix}")
        number = 2
        while candidate.exists():
            candidate = self.source.with_name(f"{self.source.stem}_trim_{number}{suffix}")
            number += 1
        return candidate

    def _save(self, overwrite: bool) -> None:
        box = self._crop_box()
        if not box:
            messagebox.showwarning("範囲未選択", "保存する範囲をドラッグして選択してください。", parent=self)
            return
        if overwrite and not messagebox.askyesno("上書き確認", f"元画像を上書きしますか？\n{self.source.name}", parent=self):
            return
        use_ai = self.transparent_var.get()
        use_lasso = self.selection_mode_var.get() == "lasso"
        force_webp = use_ai or use_lasso
        if force_webp and overwrite and self.source.suffix.lower() != ".webp":
            messagebox.showwarning(
                "WebPで保存",
                "透過画像はWebPで出力します。元画像がWebPではないため、別名で保存してください。",
                parent=self,
            )
            return
        destination = self.source if overwrite else self._trim_path(force_webp=force_webp)
        lasso = self._lasso_source_points(box) if use_lasso else []
        self.processing = True
        self.cancel_event.clear()
        self.progress_var.set(0)
        self.detect_button.configure(state="disabled")
        self.overwrite_button.configure(state="disabled")
        self.new_button.configure(state="disabled")
        self.range_var.set(tr(
            "AIモデルを準備しています…（初回はダウンロードに時間がかかります）"
            if use_ai else "保存しています…"
        ))
        threading.Thread(
            target=self._save_worker,
            args=(box, destination, overwrite, use_ai, self.model_var.get(), lasso),
            daemon=True,
        ).start()

    def _lasso_source_points(self, box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
        left, top, _right, _bottom = box
        return [
            (round((x - self.offset[0]) / self.scale) - left, round((y - self.offset[1]) / self.scale) - top)
            for x, y in self.lasso_points
        ]

    def _save_worker(self, box: tuple[int, int, int, int], destination: Path, overwrite: bool,
                     use_ai: bool, model: str, lasso: list[tuple[int, int]]) -> None:
        cropped = self.original.crop(box)
        result = cropped
        try:
            progress = lambda percent: self.ui_events.put(("progress", percent))
            result = remove_background(cropped, model, progress, self.cancel_event) if use_ai else cropped
            if lasso:
                masked = apply_lasso_mask(result, lasso)
                if result is not cropped:
                    result.close()
                result = masked
            image_format = "WEBP" if use_ai or lasso else Image.registered_extensions().get(self.source.suffix.lower(), "WEBP")
            kwargs = {"quality": self.quality} if image_format in {"WEBP", "JPEG"} else {}
            saved_image = result.convert("RGB") if image_format == "JPEG" else result
            if overwrite:
                temporary = self.source.with_name(f".{self.source.stem}_trim_tmp{self.source.suffix}")
                saved_image.save(temporary, image_format, **kwargs)
                temporary.replace(self.source)
            else:
                saved_image.save(destination, image_format, **kwargs)
            if saved_image is not result:
                saved_image.close()
            log_event("image_trimmed", source=str(self.source), output=str(destination), overwrite=overwrite,
                      crop_box=box, transparent=use_ai or bool(lasso), model=model if use_ai else "",
                      selection_mode="lasso" if lasso else "rectangle")
            self.ui_events.put(("save_succeeded", (destination, overwrite)))
        except Exception as exc:
            logging.exception("image trim failed")
            self.ui_events.put(("save_failed", str(exc)))
        finally:
            if result is not cropped:
                result.close()
            cropped.close()

    def _save_succeeded(self, destination: Path, overwrite: bool) -> None:
        self.processing = False
        self.progress_var.set(0)
        self.detect_button.configure(state="normal")
        self.on_saved(destination, overwrite)
        messagebox.showinfo("保存完了", f"保存しました。\n{destination}", parent=self)
        self._close()

    def _save_failed(self, error: str) -> None:
        self.processing = False
        self.progress_var.set(0)
        self.detect_button.configure(state="normal")
        self.overwrite_button.configure(state="normal")
        self.new_button.configure(state="normal")
        self.range_var.set(tr("保存に失敗しました"))
        messagebox.showerror("保存エラー", error, parent=self)

    def _close(self) -> None:
        if self.processing:
            self.cancel_event.set()
            self.range_var.set(tr("処理をキャンセルしています…"))
            return
        if self._ui_poll_id:
            self.after_cancel(self._ui_poll_id)
            self._ui_poll_id = None
        self.grab_release()
        self.original.close()
        self.destroy()
