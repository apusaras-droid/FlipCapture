from __future__ import annotations

import ctypes
import logging


DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_enabled = False


def enable_per_monitor_dpi_awareness() -> bool:
    """Enable physical-pixel Tk coordinates before the first window is created."""
    global _enabled
    if _enabled:
        return True
    user32 = ctypes.windll.user32
    try:
        setter = user32.SetProcessDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_bool
        if setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            _enabled = True
            logging.info("DPI awareness enabled: Per-Monitor V2")
            return True
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Windows 8.1 fallback).
        if shcore.SetProcessDpiAwareness(2) in (0, 0x80070005):
            _enabled = True
            logging.info("DPI awareness enabled: Per-Monitor V1 fallback")
            return True
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            _enabled = True
            logging.info("DPI awareness enabled: system-aware fallback")
            return True
    except (AttributeError, OSError):
        pass
    logging.warning("DPI awareness could not be changed; selection alignment may be limited")
    return False
