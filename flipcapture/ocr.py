from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .logging_setup import log_event


_JAPANESE = r"\u3040-\u30ff\u3400-\u9fff、。！？：；（）「」『』【】"


def normalize_ocr_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(fr"(?<=[{_JAPANESE}]) +(?=[{_JAPANESE}])", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


async def _recognize_path(path: Path, language_tag: str) -> str:
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile
    except ImportError as exc:
        raise RuntimeError("OCR機能が未導入です。setup.batをもう一度実行してください。") from exc

    engine = OcrEngine.try_create_from_language(Language(language_tag))
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("Windows OCRエンジンを初期化できません。日本語言語パックを確認してください。")
    file = await StorageFile.get_file_from_path_async(str(path))
    stream = await file.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        return result.text.strip()
    finally:
        stream.close()


def prepare_ocr_image(image: Image.Image, quality_mode: str = "high", max_dimension: int = 4000) -> Image.Image:
    """Prepare a screenshot for WinRT OCR without changing the source image."""
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    mode = quality_mode if quality_mode in {"standard", "high", "small_text"} else "high"
    requested_scale = {"standard": 1.0, "high": 2.0, "small_text": 3.0}[mode]
    allowed_scale = max_dimension / max(prepared.size)
    scale = min(requested_scale, allowed_scale)
    if scale != 1.0:
        size = (max(1, round(prepared.width * scale)), max(1, round(prepared.height * scale)))
        resized = prepared.resize(size, Image.Resampling.LANCZOS)
        prepared.close()
        prepared = resized
    if mode != "standard":
        gray = ImageOps.grayscale(prepared)
        prepared.close()
        adjusted = ImageOps.autocontrast(gray, cutoff=1)
        gray.close()
        gray = adjusted
        contrast = 1.20 if mode == "high" else 1.35
        adjusted = ImageEnhance.Contrast(gray).enhance(contrast)
        gray.close()
        gray = adjusted
        adjusted = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=170, threshold=2))
        gray.close()
        gray = adjusted
        prepared = gray.convert("RGB")
        gray.close()
    return prepared


def recognize_text(image: Image.Image, language_tag: str = "ja-JP", quality_mode: str = "high") -> str:
    """Recognize text locally with the Windows Runtime OCR engine."""
    prepared = prepare_ocr_image(image, quality_mode)
    try:
        with tempfile.TemporaryDirectory(prefix="flipcapture_ocr_") as name:
            path = Path(name).resolve() / "ocr_input.png"
            prepared.save(path, "PNG")
            text = normalize_ocr_text(asyncio.run(_recognize_path(path, language_tag)))
        log_event(
            "ocr_success", characters=len(text), image_size=prepared.size,
            language=language_tag, quality_mode=quality_mode,
        )
        return text
    except Exception:
        logging.exception("OCR failed")
        log_event("ocr_failure", language=language_tag)
        raise
    finally:
        prepared.close()


def recognize_text_isolated(
    image: Image.Image, timeout_seconds: int = 45, quality_mode: str = "high"
) -> str:
    """Run WinRT/COM OCR in a child process to isolate apartment/runtime failures."""
    with tempfile.TemporaryDirectory(prefix="flipcapture_ocr_job_") as name:
        path = Path(name).resolve() / "input.png"
        result_path = Path(name).resolve() / "result.json"
        image.convert("RGB").save(path, "PNG")
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        # A GUI launch uses pythonw.exe.  Use the venv's console interpreter for
        # the worker so redirected handles behave consistently on Windows.
        interpreter = Path(sys.prefix) / "python.exe"
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_event("ocr_worker_started", image_size=image.size, timeout_seconds=timeout_seconds)
        try:
            result = subprocess.run(
                [
                    str(interpreter), "-m", "flipcapture.ocr_worker",
                    str(path), str(result_path), quality_mode,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout_seconds, env=environment, creationflags=creationflags,
            )
        except subprocess.TimeoutExpired as exc:
            log_event("ocr_worker_timeout", timeout_seconds=timeout_seconds)
            raise TimeoutError(f"OCR処理が{timeout_seconds}秒を超えたため中止しました。") from exc
        if result.returncode:
            log_event("ocr_worker_failure", returncode=result.returncode, stderr=result.stderr.strip()[-500:])
            raise RuntimeError(result.stderr.strip()[-1500:] or "OCR子プロセスが異常終了しました。")
        if not result_path.exists():
            raise RuntimeError("OCR子プロセスから結果ファイルが返されませんでした。")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            text = str(payload["text"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("OCR結果ファイルを読み取れませんでした。") from exc
        log_event("ocr_worker_finished", characters=len(text))
        return text
