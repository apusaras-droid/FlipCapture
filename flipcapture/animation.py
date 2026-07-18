from __future__ import annotations

import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from .logging_setup import log_event
from .ffmpeg_support import find_ffmpeg


SUPPORTED_IMAGES = {".webp", ".png", ".jpg", ".jpeg", ".bmp"}


def _prepare(images: list[Path], width: int = 0) -> list[Image.Image]:
    if len(images) < 2:
        raise ValueError("アニメーション作成には2枚以上の画像が必要です。")
    opened: list[Image.Image] = []
    for path in images:
        if path.suffix.lower() not in SUPPORTED_IMAGES:
            continue
        image = Image.open(path).convert("RGB")
        if width > 0 and image.width != width:
            height = max(1, round(image.height * width / image.width))
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        opened.append(image)
    if len(opened) < 2:
        raise ValueError("読み込み可能な画像が2枚以上必要です。")
    canvas_size = (max(i.width for i in opened), max(i.height for i in opened))
    return [ImageOps.pad(i, canvas_size, color="black", centering=(0.5, 0.5)) for i in opened]


def default_output_path(folder: Path, extension: str) -> Path:
    return folder / f"animation_{datetime.now():%Y%m%d_%H%M%S}.{extension}"


def create_animation(
    paths: list[str | Path], output: str | Path, duration_ms: int = 150,
    loop: int = 0, width: int = 0, quality: int = 80,
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    images = _prepare([Path(p) for p in paths], width)
    duration_ms = max(30, min(5000, int(duration_ms)))
    try:
        suffix = output.suffix.lower()
        if suffix == ".webp":
            images[0].save(output, "WEBP", save_all=True, append_images=images[1:], duration=duration_ms,
                           loop=loop, quality=quality, method=6)
        elif suffix == ".gif":
            frames = [im.quantize(colors=256) for im in images]
            frames[0].save(output, "GIF", save_all=True, append_images=frames[1:], duration=duration_ms,
                           loop=loop, optimize=True, disposal=2)
        elif suffix == ".mp4":
            _create_mp4(images, output, duration_ms)
        else:
            raise ValueError("出力形式は WebP、GIF、MP4 のいずれかを指定してください。")
        log_event("animation_success", output=str(output), frames=len(images))
        return output
    except Exception:
        logging.exception("animation output failed")
        log_event("animation_failure", output=str(output))
        raise
    finally:
        for image in images:
            image.close()


def _create_mp4(images: list[Image.Image], output: Path, duration_ms: int) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpegが見つからないためMP4を出力できません。")
    with tempfile.TemporaryDirectory(prefix="flipcapture_") as temp_name:
        temp = Path(temp_name)
        concat = temp / "frames.txt"
        lines: list[str] = []
        for index, image in enumerate(images):
            frame = temp / f"frame_{index:06d}.png"
            even = ImageOps.pad(image, (image.width + image.width % 2, image.height + image.height % 2), color="black")
            even.save(frame)
            lines.extend([f"file '{frame.as_posix()}'", f"duration {duration_ms / 1000:.6f}"])
        lines.append(f"file '{(temp / f'frame_{len(images)-1:06d}.png').as_posix()}'")
        concat.write_text("\n".join(lines), encoding="utf-8")
        command = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf", "fps=30",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        logging.info("FFmpeg result (%s): %s", result.returncode, result.stderr[-4000:])
        if result.returncode:
            raise RuntimeError(f"FFmpegでのMP4出力に失敗しました。\n{result.stderr[-1000:]}")
