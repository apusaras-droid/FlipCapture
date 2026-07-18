from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable


WH_MOUSE_LL = 14
HC_ACTION = 0
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_MOUSEWHEEL = 0x020A
VK_MENU = 0x12
LLMHF_INJECTED = 0x00000001

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class MouseCaptureHook:
    """Windows mouse hook that consumes only configured Alt+mouse gestures."""

    def __init__(self, mode_getter: Callable[[], str], on_full: Callable[[], None], on_window: Callable[[], None],
                 on_ocr: Callable[[], None] | None = None):
        self.mode_getter = mode_getter
        self.on_full = on_full
        self.on_window = on_window
        self.on_ocr = on_ocr
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hook: int | None = None
        self._callback = None
        self.started = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self.started.clear()
        self._thread = threading.Thread(target=self._run, name="mouse-hook", daemon=True)
        self._thread.start()
        self.started.wait(2)
        if not self._hook:
            raise RuntimeError("マウス監視を開始できませんでした。")

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = 0

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        @HOOKPROC
        def callback(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION and user32.GetAsyncKeyState(VK_MENU) & 0x8000:
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not info.flags & LLMHF_INJECTED:
                    action = None
                    if w_param == WM_MBUTTONDOWN and self.on_ocr:
                        action = self.on_ocr
                    elif self.mode_getter() == "wheel" and w_param == WM_MOUSEWHEEL:
                        delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
                        action = self.on_full if delta > 0 else self.on_window
                    elif self.mode_getter() == "click":
                        if w_param == WM_LBUTTONDOWN:
                            action = self.on_full
                        elif w_param == WM_RBUTTONDOWN:
                            action = self.on_window
                    if action:
                        threading.Thread(target=action, daemon=True).start()
                        return 1
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._callback = callback
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, kernel32.GetModuleHandleW(None), 0)
        self.started.set()
        if not self._hook:
            logging.error("SetWindowsHookExW failed: %s", ctypes.get_last_error())
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
