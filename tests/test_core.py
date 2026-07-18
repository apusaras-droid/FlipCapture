from pathlib import Path

from PIL import Image

from flipcapture.animation import create_animation
from flipcapture.capture import CaptureService, monitor_at_point
from flipcapture.crop_dialog import apply_lasso_mask
from flipcapture.ocr import normalize_ocr_text, prepare_ocr_image
from flipcapture.image_edit import estimate_deskew_angle, line_correction_angle, rotate_image
from flipcapture.i18n import available_locales, load_locales, set_language, tr, translate_widget_tree
from flipcapture.settings import Settings, fit_window_geometry, load_settings, save_settings
from flipcapture.region_selector import physical_monitor_geometry
from flipcapture.vectorize import _clip_svg_to_alpha, vectorize_image


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    expected = Settings(
        capture_directory=str(tmp_path), capture_input_mode="click", webp_quality=72,
        run_as_admin=True, language="ja", close_to_tray=False,
        window_geometry="1100x850+120+80", selected_tab="animation",
        default_frame_duration_ms=240, default_loop_count=3, output_width=1280,
    )
    save_settings(expected, path)
    actual = load_settings(path)
    assert actual.capture_input_mode == "click"
    assert actual.webp_quality == 72
    assert actual.run_as_admin is True
    assert actual.monitoring_autostart is True
    assert actual.secondary_capture_mode == "window"
    assert actual.ocr_quality_mode == "high"
    assert actual.start_minimized_to_tray is False
    assert actual.language == "ja"
    assert actual.close_to_tray is False
    assert actual.window_geometry == "1100x850+120+80"
    assert actual.selected_tab == "animation"
    assert actual.default_frame_duration_ms == 240
    assert actual.default_loop_count == 3
    assert actual.output_width == 1280


def test_webp_and_gif_output(tmp_path: Path) -> None:
    sources = []
    for index, color in enumerate(("red", "blue")):
        source = tmp_path / f"{index}.png"
        Image.new("RGB", (31 + index, 25), color).save(source)
        sources.append(source)
    for extension in ("webp", "gif"):
        output = tmp_path / f"animation.{extension}"
        create_animation(sources, output, duration_ms=80, width=40)
        assert output.exists() and output.stat().st_size > 0
        with Image.open(output) as image:
            assert getattr(image, "n_frames", 1) == 2


def test_monitor_at_point_supports_negative_coordinates() -> None:
    monitors = [
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},
        {"left": 0, "top": 0, "width": 2560, "height": 1440},
    ]
    assert monitor_at_point(monitors, -10, 500)["left"] == -1920
    assert monitor_at_point(monitors, 100, 500)["left"] == 0


def test_saved_window_geometry_is_recovered_after_monitor_removal() -> None:
    monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
    assert fit_window_geometry("1040x840+2400+200", monitors) == "1040x840+440+120"
    assert fit_window_geometry("1040x840+200+100", monitors) == "1040x840+200+100"


def test_lasso_mask_makes_outside_transparent() -> None:
    image = Image.new("RGBA", (100, 100), "red")
    result = apply_lasso_mask(image, [(20, 20), (80, 20), (80, 80), (20, 80)], feather=0)
    alpha = result.getchannel("A")
    assert alpha.getpixel((10, 10)) == 0
    assert alpha.getpixel((50, 50)) == 255


def test_ocr_normalization_removes_spaces_between_japanese_characters() -> None:
    assert normalize_ocr_text("こ れ は テ ス ト で す 。 DXF CAD") == "これはテストです。 DXF CAD"


def test_high_quality_ocr_preprocessing_enlarges_small_text_image() -> None:
    source = Image.new("RGB", (300, 100), "white")
    prepared = prepare_ocr_image(source, "high")
    assert prepared.size == (600, 200)
    assert prepared.mode == "RGB"
    prepared.close()
    source.close()


def test_settings_falls_back_to_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(Settings(capture_directory="first"), path)
    save_settings(Settings(capture_directory="second"), path)
    path.write_text("broken", encoding="utf-8")
    assert load_settings(path).capture_directory == "first"


def test_capture_sequence_is_cached_after_first_scan(tmp_path: Path) -> None:
    service = CaptureService(Settings(capture_directory=str(tmp_path)))
    assert service._next_path().name == "capture_000001.webp"
    (tmp_path / "capture_999999.webp").touch()
    assert service._next_path().name == "capture_000002.webp"


def test_rotate_image_creates_separate_webp_with_swapped_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "sample.png"
    Image.new("RGBA", (20, 10), (255, 0, 0, 128)).save(source)
    output = rotate_image(source, 90, quality=90)
    assert output.name == "sample_rotated.webp"
    assert source.exists()
    with Image.open(output) as rotated:
        assert rotated.size == (10, 20)
    rotate_image(source, -90, overwrite=True)
    with Image.open(source) as overwritten:
        assert overwritten.size == (10, 20)


def test_manual_line_correction_uses_nearest_axis() -> None:
    assert 6.5 < line_correction_angle(0, 0, 100, 12) < 7.0
    assert -7.0 < line_correction_angle(0, 0, 12, 100) < -6.5


def test_auto_deskew_detects_rotated_straight_lines() -> None:
    from PIL import ImageDraw
    source = Image.new("RGB", (700, 360), "white")
    draw = ImageDraw.Draw(source)
    for y in range(60, 330, 55):
        draw.line((40, y, 660, y), fill="black", width=4)
    tilted = source.rotate(7, expand=True, fillcolor="white")
    correction, lines, confidence = estimate_deskew_angle(tilted)
    assert -7.5 < correction < -6.5
    assert lines >= 3
    assert confidence > 0.5
    tilted.close()
    source.close()


def test_builtin_language_files_support_english_and_japanese() -> None:
    load_locales()
    assert {locale.code for locale in available_locales()} >= {"en", "ja"}
    set_language("en")
    assert tr("監視開始") == "Start monitoring"
    set_language("ja")
    assert tr("監視開始") == "監視開始"
    set_language("en")


def test_translation_hook_ignores_destroyed_widget_path() -> None:
    translate_widget_tree(".!destroyed_widget")


def test_user_language_file_is_discovered_without_code_changes(tmp_path: Path) -> None:
    import flipcapture.i18n as i18n
    original = i18n.LOCALES_DIR
    try:
        i18n.LOCALES_DIR = tmp_path
        (tmp_path / "fr.json").write_text(
            '{"code":"fr","name":"Français","translations":{"監視開始":"Démarrer"}}',
            encoding="utf-8",
        )
        load_locales()
        assert set_language("fr") == "fr"
        assert tr("監視開始") == "Démarrer"
        assert tr("未翻訳") == "未翻訳"
    finally:
        i18n.LOCALES_DIR = original
        load_locales()
        set_language("en")


def test_opaque_image_vectorization_has_color_and_silhouette_geometry(tmp_path: Path) -> None:
    source = tmp_path / "opaque.png"
    image = Image.new("RGB", (48, 32), "navy")
    image.save(source)
    image.close()

    color_svg = tmp_path / "opaque_color.svg"
    color_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32">'
        '<path d="M 0 0 L 48 0 L 48 32 L 0 32 Z" fill="#000080"/></svg>',
        encoding="utf-8",
    )
    alpha = Image.new("L", (48, 32), 255)
    _clip_svg_to_alpha(color_svg, alpha)
    alpha.close()
    color_text = color_svg.read_text(encoding="utf-8")
    assert "<path" in color_text
    assert "subjectClip" not in color_text

    silhouette_svg, silhouette_dxf = vectorize_image(source, "silhouette")
    svg_text = silhouette_svg.read_text(encoding="utf-8")
    assert 'd="M ' in svg_text
    import ezdxf
    document = ezdxf.readfile(silhouette_dxf)
    assert len(list(document.modelspace())) >= 1


def test_mixed_dpi_selector_uses_each_monitor_physical_geometry() -> None:
    monitor_100 = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    monitor_150 = {"left": 1920, "top": 0, "width": 3840, "height": 2160}
    assert physical_monitor_geometry(monitor_100) == (0, 0, 1920, 1080)
    assert physical_monitor_geometry(monitor_150) == (1920, 0, 3840, 2160)
