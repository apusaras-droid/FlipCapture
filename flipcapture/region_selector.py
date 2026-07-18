from __future__ import annotations

import tkinter as tk
from typing import Callable

import mss
from PIL import Image, ImageTk

from .capture import monitor_at_point
from .i18n import tr
from .windows import cursor_position


def physical_monitor_geometry(monitor: dict[str, int]) -> tuple[int, int, int, int]:
    """Return the per-monitor physical rectangle used by DPI-aware Tk and MSS."""
    return tuple(int(monitor[key]) for key in ("left", "top", "width", "height"))


class RegionSelector(tk.Toplevel):
    """Freeze the monitor under the cursor and confirm a crop rectangle with Enter."""

    def __init__(self, parent: tk.Misc, on_selected: Callable[[Image.Image, tuple[int, int, int, int]], None],
                 on_cancel: Callable[[], None] | None = None,
                 instruction: str = "ドラッグで範囲指定 → Enterで保存 / Escでキャンセル"):
        super().__init__(parent)
        self.on_selected = on_selected
        self.on_cancel = on_cancel
        with mss.mss() as grabber:
            monitor = monitor_at_point(
                [dict(item) for item in grabber.monitors[1:]], *cursor_position()
            )
            shot = grabber.grab(monitor)
        monitor_left, monitor_top, monitor_width, monitor_height = physical_monitor_geometry(monitor)
        self.virtual_left = monitor_left
        self.virtual_top = monitor_top
        self.snapshot = Image.frombytes("RGB", shot.size, shot.rgb)
        source_width, source_height = self.snapshot.size

        # The process is Per-Monitor V2 aware before Tk creates its root window,
        # so Tk and MSS both use the selected monitor's physical pixel space.
        display_left, display_top = monitor_left, monitor_top
        display_width, display_height = monitor_width, monitor_height
        self.display_width = display_width
        self.display_height = display_height
        self.scale_x = source_width / display_width
        self.scale_y = source_height / display_height
        if (display_width, display_height) == self.snapshot.size:
            display_snapshot = self.snapshot
        else:
            display_snapshot = self.snapshot.resize(
                (display_width, display_height), Image.Resampling.BILINEAR
            )
        self.photo = ImageTk.PhotoImage(display_snapshot)
        if display_snapshot is not self.snapshot:
            display_snapshot.close()
        self.start: tuple[int, int] | None = None
        self.selection: tuple[int, int, int, int] | None = None
        self.rectangle: int | None = None
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{display_width}x{display_height}{display_left:+d}{display_top:+d}")
        self.canvas = tk.Canvas(
            self, cursor="crosshair", highlightthickness=0,
            width=display_width, height=display_height,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.create_rectangle(0, 0, display_width, 62, fill="black", stipple="gray50", outline="")
        self.canvas.create_text(
            display_width // 2, 30,
            text=tr(instruction),
            fill="white", font=("", 16, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", self._confirm)
        self.bind("<KP_Enter>", self._confirm)
        self.bind("<Escape>", self._cancel)
        self.focus_force()
        self.grab_set()

    def _press(self, event: tk.Event) -> None:
        self.start = (event.x, event.y)
        self.selection = None
        if self.rectangle:
            self.canvas.delete(self.rectangle)
        self.rectangle = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#00e5ff", width=4, fill=""
        )

    def _drag(self, event: tk.Event) -> None:
        if self.start and self.rectangle:
            x = max(0, min(self.display_width, event.x))
            y = max(0, min(self.display_height, event.y))
            self.canvas.coords(self.rectangle, self.start[0], self.start[1], x, y)

    def _release(self, event: tk.Event) -> None:
        if not self.start:
            return
        x = max(0, min(self.display_width, event.x))
        y = max(0, min(self.display_height, event.y))
        left, top = min(self.start[0], x), min(self.start[1], y)
        right, bottom = max(self.start[0], x), max(self.start[1], y)
        self.selection = (left, top, right, bottom) if right - left > 1 and bottom - top > 1 else None
        if self.selection:
            source_box = self._source_box(self.selection)
            self.canvas.create_text(
                left + 8, max(72, top - 12),
                text=tr("{width}×{height}  Enterで確定", width=source_box[2]-source_box[0],
                        height=source_box[3]-source_box[1]),
                fill="#00e5ff", anchor="sw", font=("", 11, "bold"), tags="size_label",
            )

    def _source_box(self, selection: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        left = max(0, min(self.snapshot.width, round(selection[0] * self.scale_x)))
        top = max(0, min(self.snapshot.height, round(selection[1] * self.scale_y)))
        right = max(left + 1, min(self.snapshot.width, round(selection[2] * self.scale_x)))
        bottom = max(top + 1, min(self.snapshot.height, round(selection[3] * self.scale_y)))
        return left, top, right, bottom

    def _confirm(self, _event: tk.Event | None = None) -> None:
        if not self.selection:
            self.bell()
            return
        source_box = self._source_box(self.selection)
        crop = self.snapshot.crop(source_box)
        absolute = (
            source_box[0] + self.virtual_left,
            source_box[1] + self.virtual_top,
            source_box[2] - source_box[0],
            source_box[3] - source_box[1],
        )
        self._finish()
        self.on_selected(crop, absolute)

    def _cancel(self, _event: tk.Event | None = None) -> None:
        self._finish()
        if self.on_cancel:
            self.on_cancel()

    def _finish(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
