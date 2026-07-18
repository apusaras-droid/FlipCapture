from __future__ import annotations

import shutil
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent


def find_ffmpeg() -> str | None:
    candidates = (
        APP_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        APP_DIR / "tools" / "ffmpeg.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")

