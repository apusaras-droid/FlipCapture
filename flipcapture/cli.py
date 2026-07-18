from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .animation import create_animation
from .capture import CaptureService
from .logging_setup import setup_logging
from .settings import load_settings
from .windows import list_windows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flipcapture", description="画面キャプチャと簡易アニメーション作成")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="GUIを起動")
    commands.add_parser("windows", help="キャプチャ可能なウィンドウを一覧表示")
    full = commands.add_parser("capture-full", help="マウスカーソルがあるモニターをキャプチャ")
    full.add_argument("--output-dir")
    window = commands.add_parser("capture-window", help="指定ウィンドウをキャプチャ")
    window.add_argument("--hwnd", type=int)
    window.add_argument("--output-dir")
    region = commands.add_parser("capture-region", help="指定した矩形座標をキャプチャ")
    region.add_argument("--left", type=int, required=True)
    region.add_argument("--top", type=int, required=True)
    region.add_argument("--width", type=int, required=True)
    region.add_argument("--height", type=int, required=True)
    region.add_argument("--output-dir")
    animate = commands.add_parser("animate", help="複数画像からアニメーションを作成")
    animate.add_argument("images", nargs="+")
    animate.add_argument("-o", "--output", required=True)
    animate.add_argument("--duration", type=int, default=150)
    animate.add_argument("--loop", type=int, default=0)
    animate.add_argument("--width", type=int, default=0)
    animate.add_argument("--quality", type=int, default=80)
    vector = commands.add_parser("vectorize", help="画像をSVGまたはDXFへベクター化")
    vector.add_argument("image")
    vector.add_argument("--mode", choices=("color", "outline", "silhouette"), required=True)
    vector.add_argument("-o", "--output")
    vector.add_argument("--dxf-internal", action="store_true", help="シルエットDXFへ内部線も出力")
    ocr = commands.add_parser("ocr", help="画像から日本語テキストをOCR")
    ocr.add_argument("image")
    ocr.add_argument("--quality", choices=("standard", "high", "small_text"), default="high")
    rotate = commands.add_parser("rotate", help="画像を90°または180°回転")
    rotate.add_argument("image")
    rotate.add_argument("--angle", type=float, required=True,
                        help="正数=左回転、負数=右回転。傾き補正は小数も指定可能")
    rotate.add_argument("-o", "--output")
    rotate.add_argument("--overwrite", action="store_true")
    rotate.add_argument("--quality", type=int, default=80)
    deskew = commands.add_parser("deskew", help="画像内の直線から傾きを自動補正")
    deskew.add_argument("image")
    deskew.add_argument("-o", "--output")
    deskew.add_argument("--overwrite", action="store_true")
    deskew.add_argument("--quality", type=int, default=80)
    deskew.add_argument("--max-angle", type=float, default=20.0)
    commands.add_parser("settings", help="現在の設定をJSON表示")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    settings = load_settings()
    from .i18n import load_locales, set_language
    load_locales()
    settings.language = set_language(settings.language)
    command = args.command or "gui"
    if command == "gui":
        from .dpi import enable_per_monitor_dpi_awareness
        enable_per_monitor_dpi_awareness()
        from .admin import is_admin, restart_as_admin
        if settings.run_as_admin and not is_admin():
            return 0 if restart_as_admin() else 1
        from .gui import run_gui
        run_gui(settings)
    elif command == "windows":
        for window in list_windows():
            print(json.dumps(asdict(window), ensure_ascii=False))
    elif command in {"capture-full", "capture-window", "capture-region"}:
        if args.output_dir:
            settings.capture_directory = args.output_dir
        service = CaptureService(settings)
        if command == "capture-full":
            path = service.capture_full()
        elif command == "capture-region":
            path = service.capture_region(args.left, args.top, args.width, args.height)
        else:
            path = service.capture_window(args.hwnd)
        print(path)
    elif command == "animate":
        path = create_animation(args.images, args.output, args.duration, args.loop, args.width, args.quality)
        print(path)
    elif command == "vectorize":
        from .vectorize import vectorize_image
        for path in vectorize_image(args.image, args.mode, args.output, args.dxf_internal):
            print(path)
    elif command == "ocr":
        from PIL import Image
        from .ocr import recognize_text_isolated
        with Image.open(args.image) as image:
            print(recognize_text_isolated(image, quality_mode=args.quality))
    elif command == "rotate":
        from .image_edit import rotate_image
        print(rotate_image(args.image, args.angle, args.output, args.overwrite, args.quality))
    elif command == "deskew":
        from .image_edit import auto_deskew_image
        path, angle, lines, confidence = auto_deskew_image(
            args.image, args.output, args.overwrite, args.quality, args.max_angle
        )
        print(path)
        print(f"correction={angle:+.3f} lines={lines} confidence={confidence:.1%}", file=sys.stderr)
    elif command == "settings":
        print(json.dumps(asdict(settings), ensure_ascii=False, indent=2))
    return 0
