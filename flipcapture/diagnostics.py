from __future__ import annotations

import importlib
import platform
import sys

from .ffmpeg_support import find_ffmpeg


REQUIRED_IMPORTS = {
    "Pillow": "PIL",
    "NumPy": "numpy",
    "SciPy": "scipy",
    "scikit-image": "skimage",
    "MSS": "mss",
    "pystray": "pystray",
    "rembg": "rembg",
    "VTracer": "vtracer",
    "ezdxf": "ezdxf",
    "Requests": "requests",
    "WinRT runtime": "winrt.runtime",
    "WinRT Foundation": "winrt.windows.foundation",
    "WinRT collections": "winrt.windows.foundation.collections",
    "WinRT globalization": "winrt.windows.globalization",
    "WinRT imaging": "winrt.windows.graphics.imaging",
    "WinRT OCR": "winrt.windows.media.ocr",
    "WinRT storage": "winrt.windows.storage",
    "WinRT streams": "winrt.windows.storage.streams",
}


def run_diagnostics() -> int:
    print(f"Python: {platform.python_version()} ({platform.architecture()[0]})")
    print(f"Platform: {platform.platform()}")
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        print("[ERROR] Supported Python versions are 3.11 through 3.13.")
        return 1

    failures: list[tuple[str, str]] = []
    for label, module_name in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            print(f"[OK] {label}")
        except Exception as exc:
            failures.append((label, str(exc)))
            print(f"[ERROR] {label}: {exc}")

    if not failures:
        try:
            from winrt.windows.media.ocr import OcrEngine

            tags = [item.language_tag for item in OcrEngine.available_recognizer_languages]
            if any(tag.lower().startswith("ja") for tag in tags):
                print("[OK] Windows Japanese OCR language")
            else:
                print("[WARN] Japanese OCR language is unavailable. Install the Japanese Windows language pack.")
        except Exception as exc:
            failures.append(("Windows OCR initialization", str(exc)))
            print(f"[ERROR] Windows OCR initialization: {exc}")

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        print(f"[OK] FFmpeg: {ffmpeg}")
    else:
        print("[WARN] FFmpeg was not found. MP4 output will be disabled; other formats remain available.")

    if failures:
        print(f"Diagnostics failed: {len(failures)} required component(s) unavailable.")
        return 1
    print("Diagnostics completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_diagnostics())
