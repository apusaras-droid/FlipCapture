from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
import mss

from .admin import is_admin, restart_as_admin
from .animation import create_animation, default_output_path
from .capture import CaptureService
from .crop_dialog import CropDialog
from .dpi import enable_per_monitor_dpi_awareness
from .ffmpeg_support import find_ffmpeg
from .fonts import register_bundled_fonts
from .i18n import (available_locales, install_tk_translation_hooks, load_locales,
                   set_language, tr, translate_widget_tree)
from .logging_setup import log_event
from .mouse_hook import MouseCaptureHook
from .ocr import recognize_text_isolated
from .region_selector import RegionSelector
from .rotate_dialog import RotateDialog
from .settings import Settings, fit_window_geometry, save_settings
from .tray import TrayController
from .vector_dialog import VectorizeDialog
from .windows import TargetWindowNotSelected, WindowInfo, list_windows
from . import __version__


class FlipCaptureApp(tk.Tk):
    def __init__(self, settings: Settings):
        enable_per_monitor_dpi_awareness()
        load_locales()
        settings.language = set_language(settings.language)
        ui_font_family = register_bundled_fonts()
        super().__init__()
        install_tk_translation_hooks(self)
        self._configure_ui_scale(ui_font_family)
        self.ui_scale = max(1.0, min(2.5, float(self.winfo_fpixels("1i")) / 96.0))
        self.settings = settings
        self._loading_ui = True
        self.capture = CaptureService(settings)
        self.windows: list[WindowInfo] = []
        self.frames: list[Path] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.preview_image: ImageTk.PhotoImage | None = None
        self.tray = TrayController(lambda action: self.events.put(("tray", action)))
        self.tray_available = False
        self._shutting_down = False
        self._poll_after_id: str | None = None
        self.hook = MouseCaptureHook(
            lambda: self.settings.capture_input_mode, self._hotkey_full, self._hotkey_secondary, self._hotkey_ocr
        )
        self.title(f"FlipCapture {__version__}")
        default_width = round(1040 * self.ui_scale)
        default_height = min(round(840 * self.ui_scale), max(700, self.winfo_screenheight() - 80))
        geometry = self.settings.window_geometry or f"{default_width}x{default_height}"
        if self.settings.window_geometry:
            try:
                with mss.mss() as grabber:
                    monitors = [dict(item) for item in grabber.monitors[1:]]
                geometry = fit_window_geometry(geometry, monitors)
                self.settings.window_geometry = geometry
            except Exception:
                logging.exception("saved window geometry could not be checked")
        self.geometry(geometry)
        self.minsize(round(880 * self.ui_scale), min(round(700 * self.ui_scale), default_height))
        self.protocol("WM_DELETE_WINDOW", self._window_close_requested)
        self.report_callback_exception = self._report_tk_exception
        self._build_ui()
        self._load_values()
        self._loading_ui = False
        translate_widget_tree(self)
        self.tray_available = self.tray.start()
        self._poll_after_id = self.after(100, self._poll_events)
        if self.settings.monitoring_autostart:
            self.after(500, self._start_monitoring)
        if self.settings.start_minimized_to_tray:
            self.after(700, self._hide_to_tray)
        log_event("app_started", language=self.settings.language, tray_available=self.tray_available)

    def _configure_ui_scale(self, family: str | None = None) -> None:
        """Use readable application-wide fonts while preserving the Windows font family."""
        font_sizes = {
            "TkDefaultFont": (11, "normal"),
            "TkTextFont": (11, "normal"),
            "TkMenuFont": (11, "normal"),
            "TkFixedFont": (11, "normal"),
            "TkHeadingFont": (11, "bold"),
            "TkCaptionFont": (11, "bold"),
            "TkSmallCaptionFont": (10, "normal"),
            "TkIconFont": (11, "normal"),
            "TkTooltipFont": (10, "normal"),
        }
        for name, (size, weight) in font_sizes.items():
            try:
                options: dict[str, object] = {"size": size, "weight": weight}
                if family:
                    options["family"] = family
                tkfont.nametofont(name).configure(**options)
            except tk.TclError:
                pass

        style = ttk.Style(self)
        style.configure(".", font="TkDefaultFont")
        style.configure("TButton", padding=(8, 5))
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("Treeview", rowheight=28)
        self.option_add("*TCombobox*Listbox.font", "TkTextFont")

    def _build_ui(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        capture_tab, animation_tab = ttk.Frame(self.notebook), ttk.Frame(self.notebook)
        self.capture_tab = capture_tab
        self.animation_tab = animation_tab
        self.notebook.add(capture_tab, text=tr("キャプチャ"))
        self.notebook.add(animation_tab, text=tr("パラパラ漫画"))
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._build_capture_tab(capture_tab)
        self._build_animation_tab(animation_tab)
        self.status_var = tk.StringVar(value=tr("監視停止中"))
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def _build_capture_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(parent, text="言語").grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.language_var = tk.StringVar()
        self.locale_items = available_locales()
        self.language_combo = ttk.Combobox(
            parent, textvariable=self.language_var,
            values=tuple(locale.name for locale in self.locale_items), state="readonly", width=22,
        )
        self.language_combo.grid(row=row, column=1, sticky="w", padx=4)
        self.language_combo.bind("<<ComboboxSelected>>", self._language_changed)
        row += 1
        ttk.Label(parent, text="入力方式").grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.mode_var = tk.StringVar()
        mode = ttk.Frame(parent)
        mode.grid(row=row, column=1, sticky="w")
        ttk.Radiobutton(mode, text="Alt＋ホイール上下", variable=self.mode_var, value="wheel", command=self._save_ui).pack(side="left")
        ttk.Radiobutton(mode, text="Alt＋左右クリック", variable=self.mode_var, value="click", command=self._save_ui).pack(side="left", padx=16)
        row += 1
        ttk.Label(parent, text="OCR操作").grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(parent, text="Alt＋マウスホイールクリック → 範囲選択 → Enterでクリップボードへコピー").grid(
            row=row, column=1, columnspan=2, sticky="w", padx=4
        )
        row += 1
        ttk.Label(parent, text="OCR画質").grid(row=row, column=0, sticky="w", padx=8, pady=4)
        self.ocr_quality_var = tk.StringVar()
        ttk.Combobox(
            parent, textvariable=self.ocr_quality_var,
            values=("標準", "高精度", "小さい文字"), state="readonly", width=14,
        ).grid(row=row, column=1, sticky="w", padx=4)
        self.ocr_quality_var.trace_add("write", lambda *_: self._save_ui())
        row += 1
        ttk.Label(parent, text="保存先").grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.folder_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.folder_var).grid(row=row, column=1, sticky="ew", padx=4)
        folder_buttons = ttk.Frame(parent)
        folder_buttons.grid(row=row, column=2, padx=8)
        ttk.Button(folder_buttons, text="選択", command=self._choose_folder).pack(side="left", padx=2)
        ttk.Button(folder_buttons, text="開く", command=self._open_folder).pack(side="left", padx=2)
        row += 1
        ttk.Label(parent, text="第2キャプチャ対象").grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.secondary_mode_var = tk.StringVar()
        secondary = ttk.Frame(parent)
        secondary.grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(secondary, text="指定ウィンドウ", variable=self.secondary_mode_var, value="window",
                        command=self._secondary_mode_changed).pack(side="left")
        ttk.Radiobutton(secondary, text="矩形範囲（毎回選択）", variable=self.secondary_mode_var, value="region",
                        command=self._secondary_mode_changed).pack(side="left", padx=16)
        row += 1
        self.window_label = ttk.Label(parent, text="指定ウィンドウ")
        self.window_label.grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.window_combo = ttk.Combobox(parent, state="readonly")
        self.window_combo.grid(row=row, column=1, sticky="ew", padx=4)
        self.window_combo.bind("<<ComboboxSelected>>", self._select_window)
        self.window_refresh_button = ttk.Button(parent, text="更新", command=self._refresh_windows)
        self.window_refresh_button.grid(row=row, column=2, padx=8)
        row += 1
        ttk.Label(parent, text="WebP画質").grid(row=row, column=0, sticky="w", padx=8, pady=8)
        self.quality_var = tk.IntVar()
        ttk.Spinbox(parent, from_=1, to=100, textvariable=self.quality_var, width=8, command=self._save_ui).grid(row=row, column=1, sticky="w", padx=4)
        row += 1
        self.lossless_var, self.timestamp_var = tk.BooleanVar(), tk.BooleanVar()
        self.notification_var, self.sound_var = tk.BooleanVar(), tk.BooleanVar()
        self.admin_var = tk.BooleanVar()
        self.autostart_var = tk.BooleanVar()
        self.close_to_tray_var = tk.BooleanVar()
        self.start_minimized_var = tk.BooleanVar()
        options = ttk.Frame(parent)
        options.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Checkbutton(options, text="可逆圧縮", variable=self.lossless_var, command=self._save_ui).pack(side="left")
        ttk.Checkbutton(options, text="ファイル名に日時を付加", variable=self.timestamp_var, command=self._save_ui).pack(side="left", padx=16)
        row += 1
        notices = ttk.Frame(parent)
        notices.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Checkbutton(notices, text="通知表示", variable=self.notification_var, command=self._save_ui).pack(side="left")
        ttk.Checkbutton(notices, text="効果音", variable=self.sound_var, command=self._save_ui).pack(side="left", padx=16)
        row += 1
        admin = ttk.Frame(parent)
        admin.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Checkbutton(admin, text="起動時に管理者権限を要求", variable=self.admin_var,
                        command=self._admin_option_changed).pack(side="left")
        self.admin_status_var = tk.StringVar()
        ttk.Label(admin, textvariable=self.admin_status_var).pack(side="left", padx=12)
        row += 1
        ttk.Checkbutton(parent, text="起動時にホットキー監視を自動開始", variable=self.autostart_var,
                        command=self._save_ui).grid(row=row, column=1, sticky="w", pady=4)
        row += 1
        tray_options = ttk.Frame(parent)
        tray_options.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            tray_options, text="閉じるボタンでタスクトレイに格納",
            variable=self.close_to_tray_var, command=self._save_ui,
        ).pack(side="left")
        ttk.Checkbutton(
            tray_options, text="起動時からタスクトレイに格納",
            variable=self.start_minimized_var, command=self._save_ui,
        ).pack(side="left", padx=16)
        row += 1
        buttons = ttk.Frame(parent)
        buttons.grid(row=row, column=0, columnspan=3, pady=18)
        self.start_button = ttk.Button(buttons, text="監視開始", command=self._start_monitoring)
        self.start_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(buttons, text="監視停止", command=self._stop_monitoring, state="disabled")
        self.stop_button.pack(side="left", padx=5)
        ttk.Button(buttons, text="カーソル位置のモニターを撮影", command=lambda: self._run_capture("full")).pack(side="left", padx=5)
        self.secondary_button = ttk.Button(buttons, command=lambda: self._run_capture("secondary"))
        self.secondary_button.pack(side="left", padx=5)
        row += 1
        info = ttk.LabelFrame(parent, text="状態")
        info.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        parent.rowconfigure(row, weight=1)
        self.info_text = tk.Text(info, height=12, state="disabled", wrap="word")
        self.info_text.pack(fill="both", expand=True, padx=6, pady=6)
        footer = ttk.Frame(parent)
        footer.grid(row=row + 1, column=0, columnspan=3, pady=8)
        ttk.Button(footer, text="保存フォルダを開く", command=self._open_folder).pack(side="left", padx=5)
        ttk.Button(footer, text="画像を一覧へ追加", command=self._load_capture_folder).pack(side="left", padx=5)

    def _build_animation_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=2)
        parent.columnconfigure(2, weight=3)
        parent.rowconfigure(0, weight=1)
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.frame_list = tk.Listbox(left, selectmode="extended")
        self.frame_list.grid(row=0, column=0, sticky="nsew")
        self.frame_list.bind("<<ListboxSelect>>", self._show_selected)
        scroll = ttk.Scrollbar(left, command=self.frame_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.frame_list.configure(yscrollcommand=scroll.set)
        controls = ttk.Frame(left)
        controls.grid(row=1, column=0, columnspan=2, pady=5)
        control_items = [
            ("追加", self._add_images), ("削除", self._remove_frames),
            ("トリミング", self._open_crop), ("回転", self._open_rotate),
            ("ベクター化", self._open_vectorize), ("上へ", lambda: self._move(-1)),
            ("下へ", lambda: self._move(1)), ("逆順", self._reverse),
        ]
        for column in range(4):
            controls.columnconfigure(column, weight=1)
        for index, (text, command) in enumerate(control_items):
            ttk.Button(controls, text=text, command=command).grid(
                row=index // 4, column=index % 4, sticky="ew", padx=2, pady=2
            )
        settings = ttk.LabelFrame(parent, text="出力設定")
        settings.grid(row=0, column=1, sticky="ns", padx=4, pady=8)
        self.duration_var, self.loop_var, self.width_var = tk.IntVar(value=150), tk.IntVar(value=0), tk.IntVar(value=0)
        self.format_var = tk.StringVar(value="webp")
        for label, var, values in [("表示時間(ms)", self.duration_var, (30, 5000)), ("ループ回数 (0=無限)", self.loop_var, (0, 999)),
                                   ("横幅 (0=元サイズ)", self.width_var, (0, 7680))]:
            ttk.Label(settings, text=label).pack(anchor="w", padx=8, pady=(9, 1))
            ttk.Spinbox(settings, from_=values[0], to=values[1], textvariable=var, width=15).pack(padx=8)
        ttk.Label(settings, text="形式").pack(anchor="w", padx=8, pady=(9, 1))
        self.ffmpeg_path = find_ffmpeg()
        logging.info("FFmpeg startup check: %s", self.ffmpeg_path or "not found; MP4 disabled")
        formats = ("webp", "gif", "mp4") if self.ffmpeg_path else ("webp", "gif")
        self.format_combo = ttk.Combobox(settings, textvariable=self.format_var, values=formats, state="readonly", width=12)
        self.format_combo.pack(padx=8)
        ttk.Label(
            settings,
            text="FFmpeg検出済み" if self.ffmpeg_path else "FFmpeg未検出: MP4無効",
            foreground="#267326" if self.ffmpeg_path else "#b00020",
        ).pack(padx=8, pady=(5, 0))
        self.animation_export_button = ttk.Button(settings, text="出力", command=self._export)
        self.animation_export_button.pack(pady=20)
        right = ttk.LabelFrame(parent, text="プレビュー")
        right.grid(row=0, column=2, sticky="nsew", padx=8, pady=8)
        self.preview_label = ttk.Label(right, text="画像を選択してください", anchor="center")
        self.preview_label.pack(fill="both", expand=True)

    def _load_values(self) -> None:
        selected_locale = next(
            (locale for locale in self.locale_items if locale.code == self.settings.language),
            self.locale_items[0],
        )
        self.language_var.set(selected_locale.name)
        self.mode_var.set(self.settings.capture_input_mode)
        self.folder_var.set(self.settings.capture_directory)
        self.quality_var.set(self.settings.webp_quality)
        self.lossless_var.set(self.settings.webp_lossless)
        self.timestamp_var.set(self.settings.include_timestamp)
        self.notification_var.set(self.settings.notification_enabled)
        self.sound_var.set(self.settings.sound_enabled)
        self.admin_var.set(self.settings.run_as_admin)
        self.autostart_var.set(self.settings.monitoring_autostart)
        self.close_to_tray_var.set(self.settings.close_to_tray)
        self.start_minimized_var.set(self.settings.start_minimized_to_tray)
        self.secondary_mode_var.set(self.settings.secondary_capture_mode)
        self.ocr_quality_labels = {
            "standard": tr("標準"), "high": tr("高精度"), "small_text": tr("小さい文字"),
        }
        self.ocr_quality_var.set(self.ocr_quality_labels.get(self.settings.ocr_quality_mode, tr("高精度")))
        self._update_secondary_button()
        self.admin_status_var.set(tr("現在: 管理者権限" if is_admin() else "現在: 通常権限"))
        self.duration_var.set(self.settings.default_frame_duration_ms)
        self.loop_var.set(self.settings.default_loop_count)
        self.width_var.set(self.settings.output_width)
        self.format_var.set(self.settings.default_output_format)
        if self.format_var.get() == "mp4" and not self.ffmpeg_path:
            self.format_var.set("webp")
        self.notebook.select(self.animation_tab if self.settings.selected_tab == "animation" else self.capture_tab)
        self._refresh_windows()

    def _save_ui(self) -> None:
        if self._loading_ui:
            return
        chosen_locale = next(
            (locale for locale in self.locale_items if locale.name == self.language_var.get()), None
        )
        if chosen_locale:
            self.settings.language = chosen_locale.code
        self.settings.capture_input_mode = self.mode_var.get()
        self.settings.capture_directory = self.folder_var.get().strip()
        self.settings.webp_quality = max(1, min(100, self.quality_var.get()))
        self.settings.webp_lossless = self.lossless_var.get()
        self.settings.include_timestamp = self.timestamp_var.get()
        self.settings.notification_enabled = self.notification_var.get()
        self.settings.sound_enabled = self.sound_var.get()
        self.settings.run_as_admin = self.admin_var.get()
        self.settings.monitoring_autostart = self.autostart_var.get()
        self.settings.close_to_tray = self.close_to_tray_var.get()
        self.settings.start_minimized_to_tray = self.start_minimized_var.get()
        self.settings.secondary_capture_mode = self.secondary_mode_var.get()
        self.settings.ocr_quality_mode = next(
            (key for key, label in self.ocr_quality_labels.items() if label == self.ocr_quality_var.get()),
            "high",
        )
        self.settings.default_frame_duration_ms = max(30, min(5000, self.duration_var.get()))
        self.settings.default_loop_count = max(0, min(999, self.loop_var.get()))
        self.settings.output_width = max(0, min(7680, self.width_var.get()))
        self.settings.default_output_format = self.format_var.get()
        self.settings.selected_tab = (
            "animation" if self.notebook.select() == str(self.animation_tab) else "capture"
        )
        if self.state() == "normal":
            self.settings.window_geometry = self.geometry()
        save_settings(self.settings)
        log_event("settings_changed", input_mode=self.settings.capture_input_mode)

    def _tab_changed(self, _event: object = None) -> None:
        self._save_ui()

    def _language_changed(self, _event: object = None) -> None:
        chosen = next(
            (locale for locale in self.locale_items if locale.name == self.language_var.get()), None
        )
        if not chosen or chosen.code == self.settings.language:
            return
        self.settings.language = chosen.code
        save_settings(self.settings)
        self.status_var.set(tr("言語を変更しています…"))
        log_event("language_changed", language=chosen.code)
        self.after(250, self._restart_application)

    def _restart_application(self) -> None:
        interpreter = Path(sys.prefix) / "pythonw.exe"
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        try:
            subprocess.Popen(
                [str(interpreter), "-m", "flipcapture", "gui"],
                cwd=Path(__file__).resolve().parent.parent,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            messagebox.showerror("FlipCapture", str(exc))
            return
        self._exit_application()

    def _secondary_mode_changed(self) -> None:
        self._save_ui()
        self._update_secondary_button()

    def _update_secondary_button(self) -> None:
        is_region = self.secondary_mode_var.get() == "region"
        text = tr("矩形範囲を撮影" if is_region else "指定ウィンドウを撮影")
        self.secondary_button.configure(text=text)
        if is_region:
            self.window_label.grid_remove()
            self.window_combo.grid_remove()
            self.window_refresh_button.grid_remove()
        else:
            self.window_label.grid()
            self.window_combo.grid()
            self.window_refresh_button.grid()

    def _begin_region_capture(self) -> None:
        was_visible = self.state() == "normal"
        if was_visible:
            self.withdraw()

        def restore() -> None:
            if was_visible:
                self.deiconify()
                self.lift()

        def open_selector() -> None:
            def selected(image: Image.Image, region: tuple[int, int, int, int]) -> None:
                restore()
                log_event("capture_region_selected", left=region[0], top=region[1], width=region[2], height=region[3])
                threading.Thread(target=self._save_region_worker, args=(image,), daemon=True).start()

            RegionSelector(self, selected, restore)

        self.after(120 if was_visible else 0, open_selector)

    def _save_region_worker(self, image: Image.Image) -> None:
        try:
            path = self.capture.save_image(image, "region")
            self.events.put(("capture", path))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            image.close()

    def _admin_option_changed(self) -> None:
        self._save_ui()
        if self.admin_var.get() and not is_admin():
            restart_now = messagebox.askyesno(
                "管理者権限で再起動",
                "設定を保存しました。今すぐ管理者権限で再起動しますか？\n"
                "Windowsのユーザーアカウント制御が表示されます。",
            )
            if restart_now:
                if restart_as_admin():
                    log_event("admin_restart_requested")
                    self._exit_application()
                else:
                    messagebox.showerror("起動エラー", "管理者権限で再起動できませんでした。")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)
            self._save_ui()

    def _refresh_windows(self) -> None:
        self.windows = list_windows()
        self.window_combo["values"] = [w.label for w in self.windows]
        index = next((i for i, w in enumerate(self.windows) if w.handle == self.settings.target_window_handle), -1)
        if index >= 0:
            self.window_combo.current(index)

    def _select_window(self, _event: object = None) -> None:
        index = self.window_combo.current()
        if index >= 0:
            window = self.windows[index]
            self.settings.target_window_handle = window.handle
            self.settings.target_window_title = window.title
            self.settings.target_process_name = window.process_name
            save_settings(self.settings)
            log_event("target_window_selected", hwnd=window.handle, title=window.title)

    def _start_monitoring(self) -> None:
        self._save_ui()
        try:
            self.hook.start()
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status_var.set(tr("ホットキー監視中"))
            log_event("monitoring_started", mode=self.settings.capture_input_mode)
        except Exception as exc:
            messagebox.showerror("監視開始エラー", str(exc))

    def _stop_monitoring(self) -> None:
        self.hook.stop()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set(tr("監視停止中"))
        log_event("monitoring_stopped")

    def _hotkey_full(self) -> None:
        self._capture_worker("full")

    def _hotkey_secondary(self) -> None:
        if self.settings.secondary_capture_mode == "region":
            self.events.put(("region_request", None))
        else:
            self._capture_worker("secondary")

    def _hotkey_ocr(self) -> None:
        self.events.put(("ocr_request", None))

    def _begin_ocr_capture(self) -> None:
        was_visible = self.state() == "normal"
        if was_visible:
            self.withdraw()

        def restore() -> None:
            if was_visible:
                self.deiconify()
                self.lift()

        def open_selector() -> None:
            def selected(image: Image.Image, region: tuple[int, int, int, int]) -> None:
                restore()
                log_event("ocr_region_selected", left=region[0], top=region[1], width=region[2], height=region[3])
                threading.Thread(target=self._ocr_worker, args=(image,), daemon=True).start()

            RegionSelector(
                self, selected, restore,
                instruction=tr("OCRする文字をドラッグで選択 → Enterで認識・コピー / Escでキャンセル"),
            )

        self.after(120 if was_visible else 0, open_selector)

    def _ocr_worker(self, image: Image.Image) -> None:
        try:
            text = recognize_text_isolated(image, quality_mode=self.settings.ocr_quality_mode)
            self.events.put(("ocr_result", text))
        except Exception as exc:
            self.events.put(("error", tr("OCRに失敗しました: {error}", error=exc)))
        finally:
            image.close()

    def _report_tk_exception(self, exc_type: type[BaseException], exc: BaseException, tb: object) -> None:
        """Keep Tk callback failures visible in the log instead of silently stopping UI work."""
        logging.error("Tk callback failed", exc_info=(exc_type, exc, tb))
        try:
            self.status_var.set(tr("画面処理エラー: {error}", error=exc))
        except tk.TclError:
            pass

    def _run_capture(self, kind: str) -> None:
        self._save_ui()
        if kind == "secondary" and self.settings.secondary_capture_mode == "region":
            self._begin_region_capture()
            return
        threading.Thread(target=self._capture_worker, args=(kind,), daemon=True).start()

    def _capture_worker(self, kind: str) -> None:
        try:
            actual_kind = self.settings.secondary_capture_mode if kind == "secondary" else kind
            if actual_kind == "full":
                path = self.capture.capture_full()
            elif actual_kind == "region":
                path = self.capture.capture_region()
            else:
                path = self.capture.capture_window()
            self.events.put(("capture", path))
        except TargetWindowNotSelected:
            # CaptureService already records the failure. An unset target is an intentional no-op.
            logging.info("window capture skipped because no target is selected")
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                try:
                    if kind == "capture":
                        self._append_info(tr("保存しました: {path}", path=value))
                        self.status_var.set(tr("最後に保存: {name}", name=Path(value).name))
                        if self.settings.sound_enabled:
                            self.bell()
                    elif kind == "error":
                        self._append_info(tr("エラー: {error}", error=value))
                        if self.settings.notification_enabled:
                            messagebox.showerror("FlipCapture", str(value))
                    elif kind == "export":
                        self.status_var.set(tr("出力しました: {path}", path=value))
                        messagebox.showinfo("出力完了", str(value))
                    elif kind == "region_request":
                        self._begin_region_capture()
                    elif kind == "ocr_request":
                        self._begin_ocr_capture()
                    elif kind == "ocr_result":
                        text = str(value)
                        log_event("ocr_result_received", characters=len(text))
                        if text.strip():
                            self.clipboard_clear()
                            self.clipboard_append(text)
                            self.update_idletasks()
                            self.status_var.set(tr("OCR結果をクリップボードへコピーしました（{count}文字）", count=len(text)))
                            self._append_info(tr("OCRコピー: {text}", text=text[:120]))
                        else:
                            self.status_var.set(tr("OCRで文字を認識できませんでした"))
                            self._append_info(tr("OCR: 文字を認識できませんでした"))
                    elif kind == "tray":
                        self._handle_tray_action(str(value))
                except Exception:
                    logging.exception("GUI event handling failed: kind=%s", kind)
        except queue.Empty:
            pass
        finally:
            if not self._shutting_down:
                try:
                    self._poll_after_id = self.after(100, self._poll_events)
                except tk.TclError:
                    self._poll_after_id = None

    def _handle_tray_action(self, action: str) -> None:
        if action == "show":
            self._show_from_tray()
        elif action == "start":
            self._start_monitoring()
        elif action == "stop":
            self._stop_monitoring()
        elif action == "folder":
            self._open_folder()
        elif action == "exit":
            self._exit_application()

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        log_event("window_restored_from_tray")

    def _hide_to_tray(self) -> None:
        if self.state() == "withdrawn":
            return
        if self.tray_available:
            self._save_ui()
            self.withdraw()
            self.tray.notify("FlipCaptureはタスクトレイで動作を続けています。")
            log_event("window_hidden_to_tray")
        else:
            self.iconify()
            self.status_var.set(tr("タスクトレイを利用できないため、ウィンドウを最小化しました。"))

    def _window_close_requested(self) -> None:
        if self.settings.close_to_tray:
            self._hide_to_tray()
        else:
            self._exit_application()

    def _append_info(self, text: str) -> None:
        self.info_text.configure(state="normal")
        self.info_text.insert("end", text + "\n")
        self.info_text.see("end")
        self.info_text.configure(state="disabled")

    def _open_folder(self) -> None:
        folder = Path(self.folder_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _load_capture_folder(self) -> None:
        folder = Path(self.folder_var.get())
        self._set_frames(sorted(folder.glob("capture_*.webp")))

    def _add_images(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[(tr("画像"), "*.webp *.png *.jpg *.jpeg *.bmp")])
        if paths:
            self._set_frames(self.frames + [Path(p) for p in paths])

    def _set_frames(self, frames: list[Path]) -> None:
        self.frames = list(dict.fromkeys(frames))
        self.frame_list.delete(0, "end")
        for frame in self.frames:
            self.frame_list.insert("end", frame.name)

    def _remove_frames(self) -> None:
        selected = set(self.frame_list.curselection())
        self._set_frames([p for i, p in enumerate(self.frames) if i not in selected])

    def _open_crop(self) -> None:
        selected = self.frame_list.curselection()
        if len(selected) != 1:
            messagebox.showwarning("画像を選択", "トリミングする画像を1枚だけ選択してください。")
            return
        CropDialog(self, self.frames[selected[0]], self.quality_var.get(), self._crop_saved)

    def _open_vectorize(self) -> None:
        selected = self.frame_list.curselection()
        if len(selected) != 1:
            messagebox.showwarning("画像を選択", "ベクター化する画像を1枚だけ選択してください。")
            return
        VectorizeDialog(self, self.frames[selected[0]])

    def _open_rotate(self) -> None:
        selected = self.frame_list.curselection()
        if len(selected) != 1:
            messagebox.showwarning("画像を選択", "回転する画像を1枚だけ選択してください。")
            return
        RotateDialog(self, self.frames[selected[0]], self.quality_var.get(), self._crop_saved)

    def _crop_saved(self, path: Path, overwrite: bool) -> None:
        if not overwrite:
            self._set_frames(self.frames + [path])
            index = len(self.frames) - 1
        else:
            index = next((i for i, frame in enumerate(self.frames) if frame == path), 0)
        self.frame_list.selection_clear(0, "end")
        self.frame_list.selection_set(index)
        self.frame_list.see(index)
        self._show_selected()

    def _move(self, direction: int) -> None:
        selected = self.frame_list.curselection()
        if len(selected) != 1:
            return
        old, new = selected[0], selected[0] + direction
        if 0 <= new < len(self.frames):
            self.frames[old], self.frames[new] = self.frames[new], self.frames[old]
            self._set_frames(self.frames)
            self.frame_list.selection_set(new)

    def _reverse(self) -> None:
        self._set_frames(list(reversed(self.frames)))

    def _show_selected(self, _event: object = None) -> None:
        selected = self.frame_list.curselection()
        if not selected:
            return
        try:
            image = Image.open(self.frames[selected[0]])
            image.thumbnail((430, 520), Image.Resampling.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.preview_image, text="")
        except OSError as exc:
            self.preview_label.configure(text=str(exc), image="")

    def _export(self) -> None:
        if len(self.frames) < 2:
            messagebox.showwarning("画像不足", "2枚以上の画像を追加してください。")
            return
        extension = self.format_var.get()
        initial = default_output_path(Path(self.folder_var.get()), extension)
        output = filedialog.asksaveasfilename(initialdir=initial.parent, initialfile=initial.name,
                                              defaultextension=f".{extension}", filetypes=[(extension.upper(), f"*.{extension}")])
        if not output:
            return
        self.settings.default_frame_duration_ms = self.duration_var.get()
        self.settings.default_loop_count = self.loop_var.get()
        self.settings.output_width = self.width_var.get()
        self.settings.default_output_format = extension
        save_settings(self.settings)
        def worker() -> None:
            try:
                result = create_animation(self.frames, output, self.duration_var.get(), self.loop_var.get(),
                                          self.width_var.get(), self.quality_var.get())
                self.events.put(("export", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _exit_application(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            if self._poll_after_id:
                try:
                    self.after_cancel(self._poll_after_id)
                except tk.TclError:
                    pass
                self._poll_after_id = None
            self._save_ui()
            self.hook.stop()
            self.tray.stop()
        finally:
            log_event("app_stopped")
            self.destroy()


def run_gui(settings: Settings) -> None:
    app = FlipCaptureApp(settings)
    app.mainloop()
