from __future__ import annotations

import os
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .logging_setup import log_event


def line_correction_angle(x1: float, y1: float, x2: float, y2: float) -> float:
    """Return the rotation that makes a drawn line horizontal or vertical."""
    if math.hypot(x2 - x1, y2 - y1) < 2:
        raise ValueError("基準線は2点を離して指定してください。")
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return ((angle + 45.0) % 90.0) - 45.0


def estimate_deskew_angle(image: Image.Image, max_angle: float = 20.0) -> tuple[float, int, float]:
    """Estimate rotation from long near-horizontal/vertical edges."""
    try:
        from skimage import feature, transform
    except ImportError as exc:
        raise RuntimeError("自動傾き補正に必要なscikit-imageが導入されていません。") from exc

    prepared = ImageOps.grayscale(ImageOps.exif_transpose(image))
    if max(prepared.size) > 1600:
        scale = 1600 / max(prepared.size)
        resized = prepared.resize(
            (round(prepared.width * scale), round(prepared.height * scale)), Image.Resampling.LANCZOS
        )
        prepared.close()
        prepared = resized
    adjusted = ImageOps.autocontrast(prepared, cutoff=1)
    prepared.close()
    prepared = adjusted
    array = np.asarray(prepared, dtype=np.float32) / 255.0
    prepared.close()
    edges = feature.canny(array, sigma=1.5)
    minimum = max(35, min(array.shape) // 7)
    lines = transform.probabilistic_hough_line(
        edges, threshold=10, line_length=minimum, line_gap=max(5, minimum // 12), rng=0
    )
    candidates: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in lines:
        length = math.hypot(x2 - x1, y2 - y1)
        correction = line_correction_angle(x1, y1, x2, y2)
        if abs(correction) <= max_angle:
            candidates.append((correction, length))
    if not candidates:
        raise ValueError("補正に使える長い直線を検出できませんでした。手動基準線を使用してください。")

    candidates.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in candidates)
    halfway = total_weight / 2
    accumulated = 0.0
    median = 0.0
    for angle, weight in candidates:
        accumulated += weight
        if accumulated >= halfway:
            median = angle
            break
    inlier_weight = sum(weight for angle, weight in candidates if abs(angle - median) <= 1.5)
    confidence = inlier_weight / total_weight if total_weight else 0.0
    return round(median, 3), len(candidates), round(confidence, 3)


def default_rotated_path(source: str | Path) -> Path:
    source_path = Path(source)
    candidate = source_path.with_name(f"{source_path.stem}_rotated.webp")
    number = 2
    while candidate.exists():
        candidate = source_path.with_name(f"{source_path.stem}_rotated_{number}.webp")
        number += 1
    return candidate


def rotate_image(
    source: str | Path,
    angle: float,
    output: str | Path | None = None,
    overwrite: bool = False,
    quality: int = 80,
) -> Path:
    """Rotate a still image counterclockwise and save it atomically."""
    source_path = Path(source)
    angle = float(angle)
    if not math.isfinite(angle) or abs(angle) > 180 or abs(angle) < 0.001:
        raise ValueError("回転角度は-180°より大きく180°以下で指定してください。")
    if overwrite and output is not None:
        raise ValueError("上書き保存と出力先指定は同時に使用できません。")
    target = source_path if overwrite else Path(output) if output else default_rotated_path(source_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.rotate.tmp")

    with Image.open(source_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    rotated = image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    image.close()
    try:
        extension = target.suffix.lower()
        if extension in {".jpg", ".jpeg", ".bmp"}:
            flattened = Image.new("RGB", rotated.size, "white")
            flattened.paste(rotated, mask=rotated.getchannel("A"))
            if extension == ".bmp":
                flattened.save(temp, "BMP")
            else:
                flattened.save(temp, "JPEG", quality=max(1, min(100, quality)))
            flattened.close()
        elif extension == ".png":
            rotated.save(temp, "PNG")
        elif extension == ".webp":
            rotated.save(temp, "WEBP", quality=max(1, min(100, quality)))
        else:
            raise ValueError("回転画像の保存形式はWebP、PNG、JPEG、BMPに対応しています。")
        os.replace(temp, target)
    finally:
        rotated.close()
        temp.unlink(missing_ok=True)
    log_event(
        "image_rotated", source=str(source_path), output=str(target),
        angle=round(angle, 3), overwrite=overwrite,
    )
    return target


def auto_deskew_image(
    source: str | Path,
    output: str | Path | None = None,
    overwrite: bool = False,
    quality: int = 80,
    max_angle: float = 20.0,
) -> tuple[Path, float, int, float]:
    """Detect long lines, correct their skew, and return output and detection details."""
    with Image.open(source) as image:
        angle, lines, confidence = estimate_deskew_angle(image, max_angle=max_angle)
    if abs(angle) < 0.05:
        raise ValueError("画像はすでにほぼ水平・垂直です。")
    path = rotate_image(source, angle, output, overwrite, quality)
    log_event("deskew_auto_saved", correction=angle, lines=lines, confidence=confidence, output=str(path))
    return path, angle, lines, confidence
