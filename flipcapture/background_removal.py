from __future__ import annotations

import threading
import hashlib
import os
import time
from pathlib import Path
from typing import Callable

import numpy as np
import requests
from PIL import Image
from scipy import ndimage


_sessions: dict[str, object] = {}
_lock = threading.Lock()
_download_lock = threading.Lock()
_verified_models: set[str] = set()
_MODEL_SPECS = {
    "u2net": ("u2net.onnx", "60024c5c889badc19c04ad937298a77b"),
    "isnet-anime": ("isnet-anime.onnx", "6f184e756bb3bd901c8849220a83e38e"),
}


def ensure_model(model: str, progress: Callable[[int], None] | None = None,
                 cancel_event: threading.Event | None = None, timeout_seconds: int = 180) -> Path | None:
    spec = _MODEL_SPECS.get(model)
    if not spec:
        return None
    filename, expected_md5 = spec
    home = Path(os.environ.get("U2NET_HOME", Path.home() / ".u2net"))
    home.mkdir(parents=True, exist_ok=True)
    destination = home / filename
    with _download_lock:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("AIモデルの取得をキャンセルしました。")
        if model in _verified_models:
            if progress:
                progress(100)
            return destination
        if destination.exists() and _file_md5(destination) == expected_md5:
            _verified_models.add(model)
            if progress:
                progress(100)
            return destination
        url = f"https://github.com/danielgatis/rembg/releases/download/v0.0.0/{filename}"
        temporary = destination.with_suffix(".download")
        started = time.monotonic()
        digest = hashlib.md5()
        try:
            with requests.get(url, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with temporary.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if cancel_event and cancel_event.is_set():
                            raise RuntimeError("AIモデルの取得をキャンセルしました。")
                        if time.monotonic() - started > timeout_seconds:
                            raise TimeoutError(f"AIモデルの取得が{timeout_seconds}秒を超えたため中止しました。")
                        if not chunk:
                            continue
                        stream.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if progress and total:
                            progress(min(99, int(downloaded * 100 / total)))
                    stream.flush()
                    os.fsync(stream.fileno())
            if digest.hexdigest() != expected_md5:
                raise RuntimeError("取得したAIモデルの検証に失敗しました。再度お試しください。")
            os.replace(temporary, destination)
            _verified_models.add(model)
            if progress:
                progress(100)
            return destination
        except requests.Timeout as exc:
            raise TimeoutError("AIモデル取得の通信がタイムアウトしました。") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"AIモデルを取得できませんでした: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session(model: str) -> object:
    try:
        from rembg import new_session
    except ImportError as exc:
        raise RuntimeError(
            "背景透過機能がインストールされていません。setup.batをもう一度実行してください。"
        ) from exc
    with _lock:
        session = _sessions.get(model)
        if session is None:
            session = new_session(model)
            _sessions[model] = session
    return session


def remove_background(image: Image.Image, model: str = "u2net",
                      progress: Callable[[int], None] | None = None,
                      cancel_event: threading.Event | None = None) -> Image.Image:
    """Return an RGBA foreground cutout. Models are loaded once per process."""
    try:
        from rembg import remove
    except ImportError as exc:
        raise RuntimeError(
            "背景透過機能がインストールされていません。setup.batをもう一度実行してください。"
        ) from exc

    ensure_model(model, progress, cancel_event)
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("背景透過処理をキャンセルしました。")
    session = _session(model)
    # Anime masks already have clean antialiased edges; alpha matting can pull
    # nearby subtitles/background colors back into the foreground.
    result = remove(image.convert("RGBA"), session=session, alpha_matting=model != "isnet-anime")
    if not isinstance(result, Image.Image):
        raise RuntimeError("背景透過処理から画像を取得できませんでした。")
    return result.convert("RGBA")


def detect_central_subject(image: Image.Image, model: str = "isnet-anime", max_dimension: int = 1280,
                           progress: Callable[[int], None] | None = None,
                           cancel_event: threading.Event | None = None) -> tuple[int, int, int, int]:
    """Detect a likely central foreground subject and return a box in source coordinates."""
    try:
        from rembg import remove
    except ImportError as exc:
        raise RuntimeError(
            "自動検出機能がインストールされていません。setup.batをもう一度実行してください。"
        ) from exc
    ensure_model(model, progress, cancel_event)
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("自動検出をキャンセルしました。")
    scale = min(1.0, max_dimension / max(image.width, image.height))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    analysis = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    mask_image = remove(analysis, session=_session(model), only_mask=True)
    if not isinstance(mask_image, Image.Image):
        raise RuntimeError("AIから検出マスクを取得できませんでした。")
    # A fairly strong threshold ignores weakly detected subtitles and browser UI.
    mask = np.asarray(mask_image.convert("L")) >= 160
    labels, count = ndimage.label(mask)
    if count == 0:
        raise ValueError("人物またはキャラクターを検出できませんでした。")

    center_x, center_y = size[0] / 2, size[1] / 2
    image_area = size[0] * size[1]
    best: tuple[float, tuple[int, int, int, int]] | None = None
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        area = len(xs)
        if area < image_area * 0.001:
            continue
        left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
        object_x, object_y = (left + right) / 2, (top + bottom) / 2
        distance = ((object_x - center_x) / size[0]) ** 2 + ((object_y - center_y) / size[1]) ** 2
        area_ratio = area / image_area
        score = area_ratio * 8.0 - distance
        if best is None or score > best[0]:
            best = (score, (left, top, right, bottom))
    if best is None:
        raise ValueError("十分な大きさの対象を検出できませんでした。")

    left, top, right, bottom = best[1]
    padding_x, padding_y = round((right - left) * 0.03), round((bottom - top) * 0.03)
    left, top = max(0, left - padding_x), max(0, top - padding_y)
    right, bottom = min(size[0], right + padding_x), min(size[1], bottom + padding_y)
    inverse = 1 / scale
    return round(left * inverse), round(top * inverse), round(right * inverse), round(bottom * inverse)
