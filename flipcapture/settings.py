from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / "config" / "settings.json"
_GEOMETRY_PATTERN = re.compile(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)")


def default_capture_directory() -> str:
    pictures = Path.home() / "Pictures"
    return str(pictures / "FlipCapture")


@dataclass
class Settings:
    language: str = "en"
    capture_directory: str = ""
    capture_input_mode: str = "wheel"
    run_as_admin: bool = False
    monitoring_autostart: bool = True
    close_to_tray: bool = True
    start_minimized_to_tray: bool = False
    window_geometry: str = ""
    selected_tab: str = "capture"
    secondary_capture_mode: str = "window"
    ocr_quality_mode: str = "high"
    webp_quality: int = 80
    webp_lossless: bool = False
    notification_enabled: bool = True
    sound_enabled: bool = False
    include_timestamp: bool = False
    default_frame_duration_ms: int = 150
    default_loop_count: int = 0
    default_output_format: str = "webp"
    output_width: int = 0
    target_window_handle: int = 0
    target_window_title: str = ""
    target_process_name: str = ""

    def __post_init__(self) -> None:
        self.language = str(self.language or "en")
        if not self.capture_directory:
            self.capture_directory = default_capture_directory()
        if self.capture_input_mode not in {"wheel", "click"}:
            self.capture_input_mode = "wheel"
        if self.secondary_capture_mode not in {"window", "region"}:
            self.secondary_capture_mode = "window"
        if self.selected_tab not in {"capture", "animation"}:
            self.selected_tab = "capture"
        if self.window_geometry and not _GEOMETRY_PATTERN.fullmatch(self.window_geometry):
            self.window_geometry = ""
        if self.ocr_quality_mode not in {"standard", "high", "small_text"}:
            self.ocr_quality_mode = "high"
        self.webp_quality = max(1, min(100, int(self.webp_quality)))


def fit_window_geometry(geometry: str, monitors: list[dict[str, int]]) -> str:
    """Move a wholly off-screen saved window onto the current primary monitor."""
    match = _GEOMETRY_PATTERN.fullmatch(geometry)
    if not match or not monitors:
        return geometry
    width, height, left, top = map(int, match.groups())
    right, bottom = left + width, top + height
    for monitor in monitors:
        monitor_right = monitor["left"] + monitor["width"]
        monitor_bottom = monitor["top"] + monitor["height"]
        if min(right, monitor_right) > max(left, monitor["left"]) and min(bottom, monitor_bottom) > max(top, monitor["top"]):
            return geometry

    primary = monitors[0]
    fitted_left = primary["left"] + max(0, (primary["width"] - min(width, primary["width"])) // 2)
    fitted_top = primary["top"] + max(0, (primary["height"] - min(height, primary["height"])) // 2)
    return f"{width}x{height}{fitted_left:+d}{fitted_top:+d}"


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        if not candidate.exists():
            continue
        try:
            data: dict[str, Any] = json.loads(candidate.read_text(encoding="utf-8"))
            known = Settings.__dataclass_fields__
            return Settings(**{k: v for k, v in data.items() if k in known})
        except (OSError, ValueError, TypeError):
            continue
    return Settings()


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        if path.exists():
            shutil.copy2(path, backup)
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        last_error: OSError | None = None
        for delay in (0.0, 0.1, 0.3):
            if delay:
                time.sleep(delay)
            try:
                os.replace(temp, path)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
    except Exception:
        if not path.exists() and backup.exists():
            shutil.copy2(backup, path)
        raise
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
