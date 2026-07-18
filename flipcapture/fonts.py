from __future__ import annotations

import ctypes
import logging
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = APP_DIR / "assets" / "fonts"
ZEN_FAMILY = "Zen Kaku Gothic New"
_FONT_FILES = (
    FONT_DIR / "ZenKakuGothicNew-Regular.ttf",
    FONT_DIR / "ZenKakuGothicNew-Bold.ttf",
)
_registered = False


def register_bundled_fonts() -> str | None:
    """Register bundled fonts privately for the current process only."""
    global _registered
    if _registered:
        return ZEN_FAMILY
    if not all(path.is_file() for path in _FONT_FILES):
        logging.warning("bundled Zen font files are missing; using system UI font")
        return None

    gdi32 = ctypes.windll.gdi32
    add_font = gdi32.AddFontResourceExW
    add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    add_font.restype = ctypes.c_int
    FR_PRIVATE = 0x10
    loaded = [add_font(str(path), FR_PRIVATE, None) > 0 for path in _FONT_FILES]
    if not all(loaded):
        logging.warning("failed to register one or more bundled Zen font files")
        return None
    _registered = True
    logging.info("UI font registered: %s", ZEN_FAMILY)
    return ZEN_FAMILY
