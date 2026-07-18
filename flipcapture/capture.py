from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

import mss
from PIL import Image

from .logging_setup import log_event
from .settings import Settings
from .windows import cursor_position, window_rect


def monitor_at_point(monitors: list[dict[str, int]], x: int, y: int) -> dict[str, int]:
    for monitor in monitors:
        if (monitor["left"] <= x < monitor["left"] + monitor["width"] and
                monitor["top"] <= y < monitor["top"] + monitor["height"]):
            return dict(monitor)
    raise RuntimeError("マウスカーソルがあるモニターを特定できません。")


class CaptureService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = Lock()
        self._sequence_directory: Path | None = None
        self._next_sequence = 1

    def _next_path(self) -> Path:
        folder = Path(self.settings.capture_directory)
        folder.mkdir(parents=True, exist_ok=True)
        resolved = folder.resolve()
        if self._sequence_directory != resolved:
            highest = 0
            for path in folder.glob("capture_*.webp"):
                try:
                    highest = max(highest, int(path.stem.split("_")[1]))
                except (IndexError, ValueError):
                    pass
            self._sequence_directory = resolved
            self._next_sequence = highest + 1
        sequence = self._next_sequence
        self._next_sequence += 1
        stem = f"capture_{sequence:06d}"
        if self.settings.include_timestamp:
            stem += datetime.now().strftime("_%Y%m%d_%H%M%S")
        return folder / f"{stem}.webp"

    def _save(self, monitor: dict[str, int], kind: str) -> Path:
        with self._lock:
            try:
                with mss.mss() as grabber:
                    shot = grabber.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                return self._save_image_unlocked(image, kind)
            except Exception:
                logging.exception("capture failed: %s", kind)
                log_event("capture_failure", kind=kind)
                raise

    def _save_image_unlocked(self, image: Image.Image, kind: str) -> Path:
        path = self._next_path()
        image.convert("RGB").save(
            path, "WEBP", quality=self.settings.webp_quality, lossless=self.settings.webp_lossless
        )
        log_event("capture_success", kind=kind, path=str(path), size=image.size)
        return path

    def save_image(self, image: Image.Image, kind: str = "region") -> Path:
        with self._lock:
            try:
                return self._save_image_unlocked(image, kind)
            except Exception:
                logging.exception("image save failed: %s", kind)
                log_event("capture_failure", kind=kind)
                raise

    def capture_full(self) -> Path:
        x, y = cursor_position()
        with mss.mss() as grabber:
            monitor = monitor_at_point([dict(item) for item in grabber.monitors[1:]], x, y)
        return self._save(monitor, "cursor_monitor")

    def capture_window(self, hwnd: int | None = None) -> Path:
        left, top, width, height = window_rect(hwnd or self.settings.target_window_handle)
        return self._save({"left": left, "top": top, "width": width, "height": height}, "window")

    def capture_region(self, left: int, top: int, width: int, height: int) -> Path:
        left_value, top_value, width_value, height_value = map(int, (left, top, width, height))
        if width_value <= 1 or height_value <= 1:
            raise ValueError("キャプチャする矩形範囲が設定されていません。")
        return self._save(
            {"left": left_value, "top": top_value, "width": width_value, "height": height_value},
            "region",
        )
