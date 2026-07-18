from __future__ import annotations

import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import feature, measure

from .logging_setup import log_event


VECTOR_MODES = {"color", "outline", "silhouette"}


def vectorize_image(source: str | Path, mode: str, output: str | Path | None = None,
                    dxf_internal_lines: bool = False) -> list[Path]:
    source = Path(source)
    if mode not in VECTOR_MODES:
        raise ValueError("ベクター化方式は color、outline、silhouette のいずれかです。")
    default_suffix = {"color": "vector_color.svg", "outline": "vector_outline.svg",
                      "silhouette": "vector_silhouette.svg"}[mode]
    output = Path(output) if output else source.with_name(f"{source.stem}_{default_suffix}")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "color":
            results = [_color_svg(source, output)]
        elif mode == "outline":
            results = [_outline_svg(source, output)]
        else:
            svg = _silhouette_svg(source, output)
            dxf_path = output.with_name(
                f"{output.stem}_internal.dxf" if dxf_internal_lines else f"{output.stem}.dxf"
            )
            dxf = _silhouette_dxf(source, dxf_path, include_internal=dxf_internal_lines)
            results = [svg, dxf]
        log_event("vectorize_success", source=str(source), mode=mode, outputs=[str(p) for p in results],
                  dxf_internal_lines=dxf_internal_lines)
        return results
    except Exception:
        logging.exception("vectorization failed")
        log_event("vectorize_failure", source=str(source), mode=mode)
        raise


def _color_svg(source: Path, output: Path) -> Path:
    try:
        import vtracer
    except ImportError as exc:
        raise RuntimeError("フルカラー変換が未導入です。setup.batをもう一度実行してください。") from exc
    with Image.open(source) as image, tempfile.TemporaryDirectory(prefix="flipcapture_vector_") as name:
        rgba = image.convert("RGBA")
        # Keeping tracing dimensions moderate prevents enormous SVG path counts.
        if max(rgba.size) > 1800:
            scale = 1800 / max(rgba.size)
            rgba = rgba.resize((round(rgba.width * scale), round(rgba.height * scale)), Image.Resampling.LANCZOS)
        png = Path(name) / "input.png"
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        white.convert("RGB").save(png, "PNG")
        vtracer.convert_image_to_svg_py(
            str(png), str(output), colormode="color", hierarchical="stacked", mode="spline",
            filter_speckle=6, color_precision=6, layer_difference=16,
            corner_threshold=60, length_threshold=4.0, max_iterations=10,
            splice_threshold=45, path_precision=2,
        )
        _clip_svg_to_alpha(output, rgba.getchannel("A"))
    return output


def _clip_svg_to_alpha(svg_path: Path, alpha: Image.Image) -> None:
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    alpha_values = np.asarray(alpha, dtype=np.float32) / 255.0
    binary = alpha_values >= 0.18
    labels, count = ndimage.label(binary)
    solid = np.zeros_like(binary)
    minimum_area = binary.size * 0.0002
    for label_id in range(1, count + 1):
        component = labels == label_id
        if component.sum() >= minimum_area:
            solid |= ndimage.binary_fill_holes(component)
    if solid.all():
        # An opaque image already occupies the full SVG viewport; clipping it
        # would add no value and find_contours has no in-array outer boundary.
        return
    contours = _mask_contours(solid, tolerance=0.8, minimum=8)
    if not contours:
        raise ValueError("透明画像の外形を取得できませんでした。")
    path_data = " ".join(_path_data(points, closed=True) for points in contours)
    original_children = list(root)
    for child in original_children:
        root.remove(child)
    definitions = ET.SubElement(root, f"{{{namespace}}}defs")
    clip = ET.SubElement(definitions, f"{{{namespace}}}clipPath", {"id": "subjectClip", "clipPathUnits": "userSpaceOnUse"})
    ET.SubElement(clip, f"{{{namespace}}}path", {"d": path_data, "clip-rule": "evenodd"})
    group = ET.SubElement(root, f"{{{namespace}}}g", {"clip-path": "url(#subjectClip)"})
    group.extend(original_children)
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)


def _load_for_trace(source: Path, max_dimension: int = 1800) -> tuple[np.ndarray, np.ndarray, float]:
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
    scale = min(1.0, max_dimension / max(rgba.size))
    if scale < 1:
        rgba = rgba.resize((round(rgba.width * scale), round(rgba.height * scale)), Image.Resampling.LANCZOS)
    array = np.asarray(rgba)
    gray = np.asarray(rgba.convert("L"), dtype=np.float32) / 255.0
    alpha = array[:, :, 3].astype(np.float32) / 255.0
    return gray, alpha, scale


def _outline_svg(source: Path, output: Path) -> Path:
    gray, alpha, _scale = _load_for_trace(source)
    contours = _internal_contours(gray, alpha)
    # Always include the transparent subject boundary.
    contours.extend(_mask_contours(alpha >= 0.18, tolerance=1.0, minimum=15))
    height, width = gray.shape
    paths = "\n".join(
        f'<path d="{_path_data(points, closed=False)}"/>' for points in contours
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<g fill="none" stroke="#111111" stroke-width="1.25" stroke-linecap="round" '
        f'stroke-linejoin="round">\n{paths}\n</g>\n</svg>\n'
    )
    output.write_text(svg, encoding="utf-8")
    return output


def _silhouette_contours(source: Path) -> tuple[list[np.ndarray], int, int]:
    _gray, alpha, _scale = _load_for_trace(source)
    contours = _mask_contours(alpha >= 0.2, tolerance=1.0, minimum=15)
    height, width = alpha.shape
    if not contours:
        raise ValueError("画像の外形を取得できませんでした。")
    return contours, width, height


def _silhouette_svg(source: Path, output: Path) -> Path:
    contours, width, height = _silhouette_contours(source)
    paths = " ".join(_path_data(points, closed=True) for points in contours)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<path d="{escape(paths)}" fill="#000000" fill-rule="evenodd"/>\n</svg>\n'
    )
    output.write_text(svg, encoding="utf-8")
    return output


def _silhouette_dxf(source: Path, output: Path, include_internal: bool = False) -> Path:
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF変換が未導入です。setup.batをもう一度実行してください。") from exc
    gray, alpha, _scale = _load_for_trace(source)
    contours = _mask_contours(alpha >= 0.2, tolerance=1.0, minimum=15)
    if not contours:
        raise ValueError("画像の外形を取得できませんでした。")
    height = alpha.shape[0]
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4  # millimeters; one image pixel is one drawing unit
    model = document.modelspace()
    for points in contours:
        xy = [(float(point[1]), float(height - point[0])) for point in points]
        model.add_lwpolyline(xy, close=True, dxfattribs={"layer": "SILHOUETTE"})
    if include_internal:
        document.layers.add("INTERNAL", color=3)
        for points in _internal_contours(gray, alpha):
            xy = [(float(point[1]), float(height - point[0])) for point in points]
            model.add_lwpolyline(xy, close=False, dxfattribs={"layer": "INTERNAL"})
    document.saveas(output)
    return output


def _internal_contours(gray: np.ndarray, alpha: np.ndarray) -> list[np.ndarray]:
    edges = feature.canny(gray, sigma=1.4, low_threshold=0.08, high_threshold=0.24, mask=alpha > 0.08)
    return _simplified_contours(edges.astype(float), 0.5, tolerance=1.2, minimum=10)


def _simplified_contours(values: np.ndarray, level: float, tolerance: float, minimum: int) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for contour in measure.find_contours(values, level):
        if len(contour) < minimum:
            continue
        simplified = measure.approximate_polygon(contour, tolerance=tolerance)
        if len(simplified) >= 3:
            result.append(simplified)
    return result


def _mask_contours(mask: np.ndarray, tolerance: float, minimum: int) -> list[np.ndarray]:
    """Trace a binary mask while treating pixels outside the image as transparent."""
    binary = np.asarray(mask, dtype=bool)
    if not binary.any():
        return []
    height, width = binary.shape
    padded = np.pad(binary.astype(np.float32), 1, mode="constant", constant_values=0)
    contours = _simplified_contours(padded, 0.5, tolerance=tolerance, minimum=minimum)
    result: list[np.ndarray] = []
    for contour in contours:
        adjusted = contour - np.array([1.0, 1.0])
        adjusted[:, 0] = np.clip(adjusted[:, 0], 0.0, float(height))
        adjusted[:, 1] = np.clip(adjusted[:, 1], 0.0, float(width))
        if len(adjusted) >= 3:
            result.append(adjusted)
    return result


def _path_data(points: np.ndarray, closed: bool) -> str:
    commands = [f"M {points[0, 1]:.2f} {points[0, 0]:.2f}"]
    commands.extend(f"L {point[1]:.2f} {point[0]:.2f}" for point in points[1:])
    if closed:
        commands.append("Z")
    return " ".join(commands)
