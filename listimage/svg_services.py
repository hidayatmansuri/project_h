"""
ListImage SVG Vector Tracing Services.
Converts cutouts or full images to pure, resolution-independent SVG vector paths.
Supports Monochrome (Silhouette & Detail), Hybrid, and Full Colour vectorization.
Uses vtracer with built-in OpenCV Bézier spline fallback.
Output is strictly pure vector: no raster images, no filters, no scripts, no CSS classes.
"""

import io
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps
from scipy.ndimage import distance_transform_edt
from django.conf import settings
from lxml import etree

logger = logging.getLogger(__name__)

# Settings & Thresholds
DEFAULT_MAX_TRACE_PX = 2000
DEFAULT_MAX_SVG_BYTES = 3 * 1024 * 1024  # 3 MB warning threshold

MAX_TRACE_PX = getattr(settings, 'LISTIMAGE_SVG_MAX_TRACE_PX', DEFAULT_MAX_TRACE_PX)
MAX_SVG_BYTES = getattr(settings, 'LISTIMAGE_SVG_MAX_BYTES', DEFAULT_MAX_SVG_BYTES)

# Presets mapping to vectorizer & vtracer parameters
PRESETS = {
    'simple': {
        'filter_speckle': 16,
        'color_precision': 4,
        'layer_difference': 24,
        'corner_threshold': 60,
        'length_threshold': 6.0,
        'splice_threshold': 45,
        'path_precision': 2,
        'epsilon_factor': 0.008,
    },
    'balanced': {
        'filter_speckle': 4,
        'color_precision': 6,
        'layer_difference': 16,
        'corner_threshold': 50,
        'length_threshold': 4.0,
        'splice_threshold': 45,
        'path_precision': 4,
        'epsilon_factor': 0.003,
    },
    'detailed': {
        'filter_speckle': 1,
        'color_precision': 8,
        'layer_difference': 8,
        'corner_threshold': 30,
        'length_threshold': 2.0,
        'splice_threshold': 40,
        'path_precision': 6,
        'epsilon_factor': 0.001,
    },
}

# SVG Namespace
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class SvgTracingError(Exception):
    """Base exception for SVG tracing and processing errors."""
    pass


def is_vtracer_available() -> bool:
    """Checks whether the vtracer binary module is available and allowed to load."""
    try:
        import vtracer
        return hasattr(vtracer, 'convert_image_to_svg_py')
    except (ImportError, OSError, Exception):
        return False


def prepare_trace_source(
    image_input: Union[Path, str, Image.Image],
    max_dim: int = MAX_TRACE_PX,
    upscale_small: bool = True
) -> Image.Image:
    """
    Loads, normalizes, and scales source image for vector tracing:
    - Never distorts or stretches (aspect ratio strictly preserved).
    - Caps longest side at max_dim (downscale with Lanczos).
    - Upscales small images (< 800px) 2x with Lanczos for smooth vector curves.
    """
    if isinstance(image_input, (str, Path)):
        img = Image.open(str(image_input))
    elif isinstance(image_input, Image.Image):
        img = image_input.copy()
    else:
        raise SvgTracingError("Invalid image input type for trace preparation.")

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    w, h = img.size
    longest = max(w, h)

    if longest > max_dim:
        scale = max_dim / float(longest)
        target_w = max(1, int(round(w * scale)))
        target_h = max(1, int(round(h * scale)))
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    elif upscale_small and longest < 800 and longest > 0:
        scale = 2.0
        target_w = int(round(w * scale))
        target_h = int(round(h * scale))
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    return img


def extract_monochrome_mask(
    rgba_image: Image.Image,
    sub_option: str = 'silhouette',
    detail_threshold: int = 128,
    use_full_image: bool = False,
    invert_detail: bool = False
) -> np.ndarray:
    """
    Extracts a binary 0/255 mask for monochrome tracing:
    - 'silhouette': traces foreground alpha mask (or luminance threshold if opaque + use_full_image).
    - 'detail': extracts internal edges / luminance features inside the foreground object.
    """
    arr = np.array(rgba_image)
    alpha = arr[:, :, 3]
    trans_mask = alpha <= 128
    has_transparency = float(np.mean(trans_mask)) > 0.02

    if sub_option == 'silhouette':
        if use_full_image and not has_transparency:
            # Grayscale thresholding of opaque full image (e.g. logo on white background)
            gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
            _, binary = cv2.threshold(gray, detail_threshold, 255, cv2.THRESH_BINARY_INV)
        else:
            # Alpha silhouette of the cutout or transparent PNG
            _, binary = cv2.threshold(alpha, 128, 255, cv2.THRESH_BINARY)
        return binary

    # 'detail' mode: inner shapes and lines
    gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
    thresh_type = cv2.THRESH_BINARY if invert_detail else cv2.THRESH_BINARY_INV
    _, binary = cv2.threshold(gray, detail_threshold, 255, thresh_type)

    # Always mask out transparent background completely (even in use_full_image mode)
    if not use_full_image or np.any(trans_mask):
        binary[trans_mask] = 0
    return binary


_SVG_TOKEN_RE = re.compile(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?')
_TRANSLATE_RE = re.compile(r'^\s*translate\(\s*([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*(?:[,\s]\s*([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?))?\s*\)\s*$')


def _parse_svg_translate(transform_str: str) -> Optional[Tuple[float, float]]:
    """Extracts (tx, ty) if transform_str is a pure translate(...) expression."""
    if not transform_str:
        return None
    m = _TRANSLATE_RE.match(transform_str)
    if not m:
        return None
    tx = float(m.group(1))
    ty = float(m.group(2)) if m.group(2) is not None else 0.0
    return (tx, ty)


def translate_svg_path_data(
    d_str: str,
    tx: float,
    ty: float,
    precision: int = 4
) -> str:
    """
    Bakes a 2D translation (tx, ty) directly into absolute SVG path commands
    so paths sit in true canvas coordinates without relying on per-path transforms.
    """
    if not d_str or (abs(tx) < 1e-9 and abs(ty) < 1e-9):
        return d_str

    tokens = _SVG_TOKEN_RE.findall(d_str)
    out: List[str] = []
    cmd = ''
    arg_i = 0

    def fmt(val: float) -> str:
        s = f"{val:.{precision}f}".rstrip('0').rstrip('.')
        return '0' if (s == '' or s == '-0') else s

    for tok in tokens:
        if tok.isalpha():
            cmd = tok
            arg_i = 0
            out.append(cmd)
            continue
        val = float(tok)
        c_upper = cmd.upper()
        if cmd.islower():
            # Only an initial relative 'm' in a path acts as absolute M for its first pair
            if cmd == 'm' and len(out) <= 2 and arg_i < 2:
                val += tx if (arg_i % 2 == 0) else ty
            out.append(fmt(val))
        else:
            if c_upper == 'H':
                out.append(fmt(val + tx))
            elif c_upper == 'V':
                out.append(fmt(val + ty))
            elif c_upper == 'A':
                mod = arg_i % 7
                out.append(fmt(val + (tx if mod == 5 else (ty if mod == 6 else 0.0))))
            else:
                out.append(fmt(val + (tx if (arg_i % 2 == 0) else ty)))
        arg_i += 1

    return ' '.join(out)


def points_to_svg_path_data(
    pts: np.ndarray,
    mode: str = 'spline',
    precision: int = 2
) -> str:
    """
    Converts 2D contour vertices into SVG path data:
    - 'polygon': Sharp straight lines (M x,y L x,y ... Z).
    - 'spline': Smooth cubic Bézier spline fitted via Catmull-Rom tangent matching.
    """
    n = len(pts)
    if n < 3:
        return ""

    if mode == 'polygon' or n < 4:
        coords = " L ".join(f"{p[0]:.{precision}f},{p[1]:.{precision}f}" for p in pts)
        return f"M {coords} Z"

    # Smooth cubic Bézier spline
    parts = [f"M {pts[0][0]:.{precision}f},{pts[0][1]:.{precision}f}"]
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]

        # Catmull-Rom to Cubic Bézier control points
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0

        parts.append(
            f"C {c1x:.{precision}f},{c1y:.{precision}f} "
            f"{c2x:.{precision}f},{c2y:.{precision}f} "
            f"{p2[0]:.{precision}f},{p2[1]:.{precision}f}"
        )
    parts.append("Z")
    return " ".join(parts)


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converts #RRGGBB or #RGB to (r, g, b) tuple."""
    h = hex_str.strip().lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Converts (r, g, b) ints (0-255) to lowercase #rrggbb."""
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def is_near_white(hex_color: str, threshold: int = 245) -> bool:
    """Checks if hex color is near-white (all channels >= threshold)."""
    r, g, b = hex_to_rgb(hex_color)
    return r >= threshold and g >= threshold and b >= threshold


def parse_svg_color(color_str: str) -> Optional[Tuple[int, int, int]]:
    """Parses hex or rgb(r,g,b) strings into (r, g, b) tuple."""
    if not color_str:
        return None
    s = color_str.strip().lower()
    if s in ('none', 'transparent'):
        return None
    if s.startswith('#'):
        return hex_to_rgb(s)
    m = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def closest_palette_index(color_str: str, palette: List[str]) -> int:
    """Finds the index of the closest palette color by Euclidean RGB distance."""
    rgb = parse_svg_color(color_str)
    if rgb is None or not palette:
        return 0
    best_idx = 0
    best_dist = float('inf')
    for idx, p_hex in enumerate(palette):
        pr, pg, pb = hex_to_rgb(p_hex)
        dist = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def trace_binary_mask_to_paths(
    binary_mask: np.ndarray,
    mode: str = 'spline',
    preset: str = 'balanced',
    color: str = '#000000',
    min_area: int = 16,
    hierarchical: str = 'stacked',
    palette_index: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Extracts 2-level contour hierarchy (outer shapes and inner cutouts/holes)
    and formats them as SVG path descriptions.
    """
    params = PRESETS.get(preset, PRESETS['balanced'])
    filter_speckle = max(params.get('filter_speckle', 4), min_area)
    precision = params.get('path_precision', 4)
    epsilon_factor = params.get('epsilon_factor', 0.003)

    # Clean tiny speckles from mask
    if filter_speckle > 1:
        kernel_size = 3 if filter_speckle < 10 else 5
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel)

    # Find contours with full 2-level hierarchy
    contours, hierarchy = cv2.findContours(binary_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    if not contours or hierarchy is None:
        return []

    hierarchy = hierarchy[0]
    paths: List[Dict[str, Any]] = []

    # Map outer contours and their immediate hole children
    for idx, (contour, h_info) in enumerate(zip(contours, hierarchy)):
        next_sib, prev_sib, first_child, parent = h_info

        # Only process outer contours at top level (parent == -1)
        if parent != -1:
            continue

        area = cv2.contourArea(contour)
        if area < filter_speckle:
            continue

        # Simplify outer contour (cap epsilon in px so large shapes retain sharp corners)
        arc_len = cv2.arcLength(contour, True)
        epsilon = min(2.5, max(0.5, arc_len * epsilon_factor))
        approx_outer = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(approx_outer) < 3:
            continue

        d_outer = points_to_svg_path_data(approx_outer, mode=mode, precision=precision)
        d_subpaths = [d_outer]

        # Gather any hole contours belonging to this shape
        child_idx = first_child
        while child_idx != -1:
            child_contour = contours[child_idx]
            child_area = cv2.contourArea(child_contour)
            if child_area >= filter_speckle // 2:
                child_len = cv2.arcLength(child_contour, True)
                child_eps = min(2.0, max(0.5, child_len * epsilon_factor))
                approx_child = cv2.approxPolyDP(child_contour, child_eps, True).reshape(-1, 2)
                if len(approx_child) >= 3:
                    d_child = points_to_svg_path_data(approx_child, mode=mode, precision=precision)
                    d_subpaths.append(d_child)
            child_idx = hierarchy[child_idx][0]  # Next child

        full_d = " ".join(d_subpaths).strip()
        if full_d:
            p_dict: Dict[str, Any] = {
                'd': full_d,
                'fill': color,
                'fill_rule': 'evenodd',
            }
            if palette_index is not None:
                p_dict['palette_index'] = palette_index
            paths.append(p_dict)

    return paths


def sanitize_svg(svg_xml_content: str) -> str:
    """
    Strictly sanitizes SVG XML:
    - Verifies well-formed XML using lxml.etree.
    - Removes all disallowed elements: script, image, foreignObject, filter, style, use, iframe.
    - Strips event attributes (on*) and javascript: links.
    - Enforces shape-rendering="geometricPrecision" and preserveAspectRatio="xMidYMid meet".
    - Guarantees pure vector paths only.
    """
    if not svg_xml_content or not svg_xml_content.strip():
        raise SvgTracingError("Empty SVG content received for sanitization.")

    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(svg_xml_content.encode('utf-8'), parser=parser)
    except Exception as e:
        raise SvgTracingError(f"Malformed SVG XML: {e}") from e

    # Ensure root is <svg>
    tag_name = etree.QName(root.tag).localname
    if tag_name.lower() != 'svg':
        raise SvgTracingError(f"Root element must be <svg>, found <{tag_name}>.")

    # Disallowed elements
    DISALLOWED_TAGS = {
        'script', 'image', 'foreignobject', 'filter', 'style',
        'use', 'iframe', 'object', 'embed', 'audio', 'video',
        'fecomponenttransfer', 'fegaussianblur', 'feblend',
    }

    # Remove dangerous and raster elements
    for el in list(root.iter()):
        local = etree.QName(el.tag).localname.lower()
        if local in DISALLOWED_TAGS:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
            continue

        # Clean attributes
        for attr in list(el.attrib.keys()):
            attr_lower = attr.lower()
            val = el.attrib[attr].strip().lower()
            if attr_lower.startswith('on') or 'javascript:' in val:
                del el.attrib[attr]

    # Enforce SVG rendering standards
    root.attrib['preserveAspectRatio'] = "xMidYMid meet"
    root.attrib['shape-rendering'] = "geometricPrecision"
    if 'xmlns' not in root.attrib and None not in root.nsmap:
        root.attrib['xmlns'] = SVG_NS

    return etree.tostring(root, encoding='utf-8', pretty_print=True).decode('utf-8')


def build_svg_document(
    paths: List[Dict[str, Any]],
    view_width: int,
    view_height: int,
    square_canvas: bool = False,
    bg_color: str = 'transparent',
    title: str = "Traced Vector Image",
    desc: str = "Generated by project-h ListImage"
) -> str:
    """
    Builds a clean, resolution-independent SVG document from path dictionaries.
    Handles exact viewBox matching, square 1:1 canvas centering, and title/desc accessibility.
    """
    root = etree.Element(
        etree.QName(SVG_NS, 'svg'),
        nsmap={None: SVG_NS}
    )
    root.attrib['preserveAspectRatio'] = "xMidYMid meet"
    root.attrib['shape-rendering'] = "geometricPrecision"

    if square_canvas:
        # Center in square viewBox with 5% padding
        square_dim = max(view_width, view_height)
        padding = max(10, int(round(square_dim * 0.05)))
        total_dim = square_dim + (2 * padding)
        offset_x = padding + (square_dim - view_width) // 2
        offset_y = padding + (square_dim - view_height) // 2

        root.attrib['viewBox'] = f"0 0 {total_dim} {total_dim}"

        # Optional white background
        if bg_color == 'white':
            bg_rect = etree.SubElement(root, etree.QName(SVG_NS, 'rect'))
            bg_rect.attrib['width'] = "100%"
            bg_rect.attrib['height'] = "100%"
            bg_rect.attrib['fill'] = "#ffffff"

        container = etree.SubElement(root, etree.QName(SVG_NS, 'g'))
        if offset_x != 0 or offset_y != 0:
            container.attrib['transform'] = f"translate({offset_x}, {offset_y})"
    else:
        root.attrib['viewBox'] = f"0 0 {view_width} {view_height}"
        if bg_color == 'white':
            bg_rect = etree.SubElement(root, etree.QName(SVG_NS, 'rect'))
            bg_rect.attrib['width'] = "100%"
            bg_rect.attrib['height'] = "100%"
            bg_rect.attrib['fill'] = "#ffffff"
        container = root

    # Accessibility metadata
    title_el = etree.SubElement(root, etree.QName(SVG_NS, 'title'))
    title_el.text = title
    desc_el = etree.SubElement(root, etree.QName(SVG_NS, 'desc'))
    desc_el.text = desc

    # Append paths
    for p in paths:
        d_val = p.get('d', '').strip()
        if not d_val:
            continue
        path_el = etree.SubElement(container, etree.QName(SVG_NS, 'path'))
        path_el.attrib['d'] = d_val
        path_el.attrib['fill'] = p.get('fill', '#000000')
        if p.get('fill_rule'):
            path_el.attrib['fill-rule'] = p['fill_rule']
        if p.get('palette_index') is not None:
            path_el.attrib['data-palette-index'] = str(p['palette_index'])
        if p.get('transform'):
            path_el.attrib['transform'] = p['transform']

    raw_svg = etree.tostring(root, encoding='utf-8', pretty_print=True).decode('utf-8')
    return sanitize_svg(raw_svg)


def get_svg_stats(svg_content: str) -> Dict[str, Any]:
    """
    Computes SVG diagnostics: path count, unique colors, byte size,
    viewBox, and warns if size exceeds LISTIMAGE_SVG_MAX_BYTES.
    """
    byte_size = len(svg_content.encode('utf-8'))
    warn_large = byte_size > MAX_SVG_BYTES

    try:
        parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
        root = etree.fromstring(svg_content.encode('utf-8'), parser=parser)
        paths = list(root.iter(f"{{{SVG_NS}}}path"))
        fills: Set[str] = set()
        for p in paths:
            f = p.attrib.get('fill')
            if f and f.lower() not in ('none', 'transparent'):
                fills.add(f.lower())

        viewbox = root.attrib.get('viewBox', '')
        return {
            'path_count': len(paths),
            'color_count': len(fills),
            'colors': sorted(list(fills)),
            'file_size': byte_size,
            'file_size_formatted': f"{byte_size / (1024 * 1024):.2f} MB" if byte_size >= 1024 * 1024 else f"{byte_size / 1024:.1f} KB",
            'viewBox': viewbox,
            'warn_large': warn_large,
        }
    except Exception as e:
        logger.warning("Could not compute SVG stats: %s", e)
        return {
            'path_count': 0,
            'color_count': 0,
            'colors': [],
            'file_size': byte_size,
            'file_size_formatted': f"{byte_size / 1024:.1f} KB",
            'viewBox': '',
            'warn_large': warn_large,
        }


def _run_vtracer_and_extract_paths(
    rgba_array: np.ndarray,
    colormode: str,
    preset: str = 'balanced',
    mode: str = 'spline',
    hierarchical: str = 'stacked',
    custom_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Runs vtracer on an in-memory RGBA numpy array, cleans up temp files, bakes
    per-path translate(tx, ty) transforms directly into canvas coordinates,
    and returns extracted path dictionaries.
    """
    import tempfile
    import vtracer

    preset_params = PRESETS.get(preset, PRESETS['balanced']).copy()
    if custom_params:
        preset_params.update({k: v for k, v in custom_params.items() if v is not None})

    precision = int(preset_params.get('path_precision', 4))
    tmp_in_path = None
    tmp_out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_in:
            tmp_in_path = tmp_in.name
            Image.fromarray(rgba_array, mode='RGBA').save(tmp_in_path, format='PNG')

        with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as tmp_out:
            tmp_out_path = tmp_out.name

        vtracer.convert_image_to_svg_py(
            image_path=tmp_in_path,
            out_path=tmp_out_path,
            colormode=colormode,
            hierarchical=hierarchical,
            mode=mode,
            filter_speckle=int(preset_params.get('filter_speckle', 4)),
            color_precision=int(preset_params.get('color_precision', 6)),
            layer_difference=int(preset_params.get('layer_difference', 16)),
            corner_threshold=int(preset_params.get('corner_threshold', 50)),
            length_threshold=float(preset_params.get('length_threshold', 4.0)),
            splice_threshold=int(preset_params.get('splice_threshold', 45)),
            path_precision=precision,
        )

        with open(tmp_out_path, 'r', encoding='utf-8') as f:
            vtracer_svg = f.read()
    finally:
        if tmp_in_path:
            Path(tmp_in_path).unlink(missing_ok=True)
        if tmp_out_path:
            Path(tmp_out_path).unlink(missing_ok=True)

    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    vroot = etree.fromstring(vtracer_svg.encode('utf-8'), parser=parser)
    extracted: List[Dict[str, Any]] = []

    for p_el in vroot.iter(f"{{{SVG_NS}}}path"):
        d_val = p_el.attrib.get('d', '').strip()
        f_val = p_el.attrib.get('fill', '').strip()
        if not d_val:
            continue

        raw_transform = p_el.attrib.get('transform', '').strip()
        parsed_translate = _parse_svg_translate(raw_transform)
        remaining_transform = ''
        if parsed_translate is not None:
            d_val = translate_svg_path_data(d_val, parsed_translate[0], parsed_translate[1], precision=precision)
        elif raw_transform:
            remaining_transform = raw_transform

        p_item: Dict[str, Any] = {
            'd': d_val,
            'fill': f_val,
            'fill_rule': p_el.attrib.get('fill-rule', 'evenodd'),
        }
        if remaining_transform:
            p_item['transform'] = remaining_transform
        extracted.append(p_item)

    return extracted


def trace_monochrome(
    image_input: Union[Path, str, Image.Image],
    sub_option: str = 'silhouette',
    color: str = '#000000',
    detail_threshold: int = 128,
    preset: str = 'balanced',
    mode: str = 'spline',
    hierarchical: str = 'stacked',
    use_full_image: bool = False,
    square_canvas: bool = False,
    bg_color: str = 'transparent',
    custom_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Traces source image in Monochrome mode:
    - sub_option: 'silhouette' (alpha mask) or 'detail' (internal line/shape detail).
    - color: One user-chosen color (default black #000000).
    - Returns (sanitized_svg_string, svg_stats_dict).
    """
    # 1. Normalize and scale source
    prep_img = prepare_trace_source(image_input, max_dim=MAX_TRACE_PX)
    w, h = prep_img.size

    # 2. Extract monochrome binary mask (255 = foreground, 0 = background)
    binary_mask = extract_monochrome_mask(
        prep_img,
        sub_option=sub_option,
        detail_threshold=detail_threshold,
        use_full_image=use_full_image
    )

    # 3. Vectorize paths (only if foreground pixels exist)
    paths: List[Dict[str, Any]] = []
    fg_bool = binary_mask > 127

    if np.any(fg_bool) and is_vtracer_available():
        try:
            # vtracer(colormode='binary') traces black foreground on white background
            bin_rgba = np.empty((h, w, 4), dtype=np.uint8)
            bin_rgba[fg_bool] = [0, 0, 0, 255]
            bin_rgba[~fg_bool] = [255, 255, 255, 255]

            raw_paths = _run_vtracer_and_extract_paths(
                rgba_array=bin_rgba,
                colormode='binary',
                preset=preset,
                mode=mode,
                hierarchical=hierarchical,
                custom_params=custom_params,
            )
            for p_item in raw_paths:
                f_val = p_item.get('fill', '').lower()
                if f_val in ('#ffffff', 'white', 'rgb(255,255,255)'):
                    continue
                p_item['fill'] = color
                paths.append(p_item)
        except Exception as e:
            logger.warning("vtracer execution failed (%s), falling back to OpenCV Bézier vectorizer", e)
            paths = []

    # Fallback to OpenCV Bézier vectorizer if needed
    if np.any(fg_bool) and not paths:
        paths = trace_binary_mask_to_paths(
            binary_mask=binary_mask,
            mode=mode,
            preset=preset,
            color=color,
            hierarchical=hierarchical
        )

    # 4. Construct final sanitized SVG document
    svg_document = build_svg_document(
        paths=paths,
        view_width=w,
        view_height=h,
        square_canvas=square_canvas,
        bg_color=bg_color,
        title=f"Traced Vector - {sub_option.capitalize()}",
        desc=f"Monochrome {sub_option} vectorization"
    )

    stats = get_svg_stats(svg_document)
    return svg_document, stats


def quantize_palette_kmeans(
    rgba_image: Image.Image,
    n_colors: int = 8,
    use_full_image: bool = False
) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """
    Quantizes foreground colors into n_colors (2 to 16) using OpenCV K-Means clustering:
    - Always respects existing transparent pixels (alpha <= 128) so background never becomes black.
    - De-fringes semi-transparent anti-aliased borders from pure interior pixels to eliminate halo artifacts.
    Returns:
    - quantized_indices: 2D np.ndarray (H, W) with palette indices (0 to K-1) or -1 for background.
    - palette: List of hex color strings (e.g. ['#112233', ...]) ordered by frequency (most dominant first).
    - quantized_rgb: 3D np.ndarray (H, W, 3) reconstructed quantized RGB image.
    """
    n_colors = max(2, min(16, int(n_colors)))
    arr = np.array(rgba_image)
    h, w = arr.shape[:2]
    alpha = arr[:, :, 3]

    has_transparency = np.any(alpha <= 128)
    if use_full_image and not has_transparency:
        fg_mask = np.ones((h, w), dtype=bool)
    else:
        fg_mask = alpha > 128

    if not np.any(fg_mask):
        palette = ['#000000']
        indices = np.full((h, w), -1, dtype=np.int32)
        quant_rgb = np.zeros((h, w, 3), dtype=np.uint8)
        return indices, palette, quant_rgb

    # Identify pure core interior pixels free of anti-aliased edge blending
    core_mask = fg_mask & (alpha >= 248)
    if np.any(core_mask):
        eroded = cv2.erode(
            core_mask.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        ) > 0
        if eroded.sum() >= max(100, int(fg_mask.sum() * 0.25)):
            sample_mask = eroded
        elif core_mask.sum() >= max(50, int(fg_mask.sum() * 0.1)):
            sample_mask = core_mask
        else:
            sample_mask = fg_mask
    else:
        sample_mask = fg_mask

    # Propagate nearest core interior pixel RGB outward onto anti-aliased fringe & thin tips
    clean_rgb = arr[:, :, :3].copy()
    fringe = fg_mask & ~sample_mask
    if np.any(fringe) and np.any(sample_mask):
        nearest_yx = distance_transform_edt(~sample_mask, return_distances=False, return_indices=True)
        clean_rgb[fringe] = arr[nearest_yx[0][fringe], nearest_yx[1][fringe], :3]

    core_pixels = clean_rgb[sample_mask]
    unique_core = np.unique(core_pixels, axis=0)
    if len(unique_core) == 1:
        c = unique_core[0]
        palette = [rgb_to_hex(c[0], c[1], c[2])]
        quantized_indices = np.full((h, w), -1, dtype=np.int32)
        quantized_indices[fg_mask] = 0
        quantized_rgb = np.zeros((h, w, 3), dtype=np.uint8)
        quantized_rgb[fg_mask] = c
        return quantized_indices, palette, quantized_rgb

    # Gently smooth compression/gradient grain before clustering when colors exceed palette slots
    if len(unique_core) > n_colors:
        clean_rgb = cv2.bilateralFilter(clean_rgb, d=9, sigmaColor=18, sigmaSpace=9)
        core_pixels = clean_rgb[sample_mask]
        unique_core = np.unique(core_pixels, axis=0)

    actual_k = min(n_colors, len(unique_core))
    if len(core_pixels) > 250000:
        # Subsample deterministically for fast K-Means convergence on ultra-large images
        step = max(1, len(core_pixels) // 250000)
        kmeans_input = core_pixels[::step].astype(np.float32)
    else:
        kmeans_input = core_pixels.astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5)
    _, _, centers = cv2.kmeans(
        kmeans_input,
        actual_k,
        None,
        criteria,
        10,
        cv2.KMEANS_PP_CENTERS
    )
    centers_f32 = centers.astype(np.float32)
    centers_u8 = np.uint8(np.clip(centers_f32, 0, 255))

    # Map all foreground pixels to their nearest centroid
    all_fg = clean_rgb[fg_mask].astype(np.float32)
    nearest_raw = ((all_fg[:, None, :] - centers_f32[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)

    # Interior-only 5x5 median pass suppresses single-pixel speckles along gradients without blunting thin tips
    if len(unique_core) > n_colors:
        q_rgb_tmp = np.zeros((h, w, 3), dtype=np.uint8)
        q_rgb_tmp[fg_mask] = centers_u8[nearest_raw]
        med_rgb = cv2.medianBlur(q_rgb_tmp, 5)
        inner_safe = cv2.erode(fg_mask.astype(np.uint8), np.ones((5, 5), dtype=np.uint8)) > 0
        q_rgb_tmp[inner_safe] = med_rgb[inner_safe]
        all_fg_final = q_rgb_tmp[fg_mask].astype(np.float32)
        nearest_final = ((all_fg_final[:, None, :] - centers_f32[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    else:
        nearest_final = nearest_raw

    # Sort palette descending by pixel dominance in foreground
    counts = np.bincount(nearest_final, minlength=actual_k)
    sorted_order = [i for i in np.argsort(-counts) if counts[i] > 0]
    if not sorted_order:
        sorted_order = list(range(actual_k))

    label_remap = np.full(actual_k, 0, dtype=np.int32)
    palette: List[str] = []
    for new_idx, old_idx in enumerate(sorted_order):
        label_remap[old_idx] = new_idx
        c = centers_u8[old_idx]
        palette.append(rgb_to_hex(c[0], c[1], c[2]))

    quantized_indices = np.full((h, w), -1, dtype=np.int32)
    quantized_indices[fg_mask] = label_remap[nearest_final]

    quantized_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for idx, hex_color in enumerate(palette):
        quantized_rgb[quantized_indices == idx] = hex_to_rgb(hex_color)

    return quantized_indices, palette, quantized_rgb


def apply_palette_recoloring(
    svg_content: str,
    palette_map: Dict[Union[int, str], Optional[str]],
    remove_near_white: bool = False,
    near_white_threshold: int = 245
) -> Tuple[str, Dict[str, Any]]:
    """
    Applies palette-to-colour mapping server-side to produce the final SVG:
    - palette_map maps palette index (int or str) -> replacement hex color (or None/'transparent' to remove).
    - If remove_near_white is True, elements with fills where R, G, B >= near_white_threshold are removed.
    - Strictly returns sanitized SVG string and updated stats.
    """
    if not svg_content or not svg_content.strip():
        raise SvgTracingError("Empty SVG content for recoloring.")

    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(svg_content.encode('utf-8'), parser=parser)
    except Exception as e:
        raise SvgTracingError(f"Malformed SVG in recoloring: {e}") from e

    str_map = {str(k): v for k, v in palette_map.items()}
    elements_to_remove = []

    for el in root.iter():
        tag_local = etree.QName(el.tag).localname.lower()
        if tag_local not in ('path', 'polygon', 'rect', 'circle', 'ellipse'):
            continue

        p_idx = el.attrib.get('data-palette-index')
        current_fill = el.attrib.get('fill', '').strip()

        # Check palette map replacement
        if p_idx is not None and str(p_idx) in str_map:
            new_col = str_map[str(p_idx)]
            if new_col is None or new_col.lower() in ('transparent', 'none', ''):
                elements_to_remove.append(el)
                continue
            else:
                el.attrib['fill'] = new_col
                current_fill = new_col

        # Check remove near-white
        if remove_near_white and current_fill:
            if is_near_white(current_fill, threshold=near_white_threshold):
                elements_to_remove.append(el)
                continue

    # Remove discarded elements
    for el in elements_to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    raw_recolored = etree.tostring(root, encoding='utf-8', pretty_print=True).decode('utf-8')
    sanitized = sanitize_svg(raw_recolored)
    stats = get_svg_stats(sanitized)
    return sanitized, stats


def trace_full_color(
    image_input: Union[Path, str, Image.Image],
    n_colors: int = 8,
    preset: str = 'balanced',
    mode: str = 'spline',
    hierarchical: str = 'stacked',
    use_full_image: bool = False,
    square_canvas: bool = False,
    bg_color: str = 'transparent',
    custom_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Traces source image in Full Colour mode:
    - Quantizes into 2-16 discrete palette colors via OpenCV K-Means.
    - Tags every vector path with data-palette-index="<index>".
    - Dual-engine: vtracer (with palette-tagging post-processor) or OpenCV Bézier contour tracer.
    - Returns (sanitized_svg_string, svg_stats_dict, palette_list).
    """
    prep_img = prepare_trace_source(image_input, max_dim=MAX_TRACE_PX)
    w, h = prep_img.size

    quant_indices, palette, quant_rgb = quantize_palette_kmeans(
        prep_img,
        n_colors=n_colors,
        use_full_image=use_full_image
    )

    paths: List[Dict[str, Any]] = []
    fg_mask = quant_indices >= 0

    if np.any(fg_mask) and is_vtracer_available():
        try:
            # Build crisp-alpha RGBA input (transparent bg with white fill so zero black fringe occurs)
            q_rgba = np.empty((h, w, 4), dtype=np.uint8)
            q_rgba[~fg_mask] = [255, 255, 255, 0]
            q_rgba[fg_mask, :3] = quant_rgb[fg_mask]
            q_rgba[fg_mask, 3] = 255

            raw_paths = _run_vtracer_and_extract_paths(
                rgba_array=q_rgba,
                colormode='color',
                preset=preset,
                mode=mode,
                hierarchical=hierarchical,
                custom_params=custom_params,
            )
            for p_item in raw_paths:
                f_val = p_item.get('fill', '').strip()
                if not f_val or f_val.lower() in ('none', 'transparent'):
                    continue
                p_idx = closest_palette_index(f_val, palette)
                p_item['fill'] = palette[p_idx]
                p_item['palette_index'] = p_idx
                paths.append(p_item)
        except Exception as e:
            logger.warning("vtracer full-color trace failed (%s), falling back to OpenCV vectorizer", e)
            paths = []

    # OpenCV fallback: trace each palette layer
    if np.any(fg_mask) and not paths:
        for idx in range(len(palette)):
            layer_mask = (quant_indices == idx).astype(np.uint8) * 255
            layer_paths = trace_binary_mask_to_paths(
                binary_mask=layer_mask,
                mode=mode,
                preset=preset,
                color=palette[idx],
                hierarchical=hierarchical,
                palette_index=idx
            )
            paths.extend(layer_paths)

    svg_document = build_svg_document(
        paths=paths,
        view_width=w,
        view_height=h,
        square_canvas=square_canvas,
        bg_color=bg_color,
        title="Traced Vector Image - Full Colour",
        desc=f"Full colour vectorization with {len(palette)} colors"
    )

    stats = get_svg_stats(svg_document)
    return svg_document, stats, palette


def trace_hybrid(
    image_input: Union[Path, str, Image.Image],
    kept_indices: Optional[List[int]] = None,
    monochrome_color: str = '#000000',
    n_colors: int = 8,
    preset: str = 'balanced',
    mode: str = 'spline',
    hierarchical: str = 'stacked',
    use_full_image: bool = False,
    square_canvas: bool = False,
    bg_color: str = 'transparent',
    custom_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Traces source image in Hybrid mode:
    - Chosen parts (kept_indices) keep their color; everything else becomes monochrome_color.
    - If kept_indices is None, defaults to [0] (most dominant color keeps original, others monochrome).
    - Returns (sanitized_svg_string, svg_stats_dict, palette_list).
    """
    svg_doc, stats, palette = trace_full_color(
        image_input=image_input,
        n_colors=n_colors,
        preset=preset,
        mode=mode,
        hierarchical=hierarchical,
        use_full_image=use_full_image,
        square_canvas=square_canvas,
        bg_color=bg_color,
        custom_params=custom_params
    )

    if kept_indices is None:
        kept_indices = [0]
    kept_set = set(kept_indices)

    # Build palette map: kept indices keep their hex color, other indices map to monochrome_color
    palette_map: Dict[int, Optional[str]] = {}
    for idx, hex_col in enumerate(palette):
        if idx in kept_set:
            palette_map[idx] = hex_col
        else:
            palette_map[idx] = monochrome_color

    hybrid_svg, hybrid_stats = apply_palette_recoloring(svg_doc, palette_map)
    return hybrid_svg, hybrid_stats, palette


def trace_image_to_svg(
    image_input: Union[Path, str, Image.Image],
    color_mode: str = 'monochrome',  # 'monochrome', 'hybrid', 'full'
    sub_option: str = 'silhouette',
    color: str = '#000000',
    detail_threshold: int = 128,
    n_colors: int = 8,
    kept_indices: Optional[List[int]] = None,
    monochrome_color: str = '#000000',
    palette_map: Optional[Dict[Union[int, str], Optional[str]]] = None,
    remove_near_white: bool = False,
    preset: str = 'balanced',
    mode: str = 'spline',
    hierarchical: str = 'stacked',
    use_full_image: bool = False,
    square_canvas: bool = False,
    bg_color: str = 'transparent',
    custom_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Unified dispatcher for SVG vectorization:
    - color_mode: 'monochrome' | 'hybrid' | 'full'
    - Applies server-side palette recoloring or near-white removal if requested.
    - Returns (svg_document_string, svg_stats_dict, palette_list).
    """
    color_mode = color_mode.lower()

    if color_mode == 'monochrome':
        svg_doc, stats = trace_monochrome(
            image_input=image_input,
            sub_option=sub_option,
            color=color,
            detail_threshold=detail_threshold,
            preset=preset,
            mode=mode,
            hierarchical=hierarchical,
            use_full_image=use_full_image,
            square_canvas=square_canvas,
            bg_color=bg_color,
            custom_params=custom_params
        )
        palette = [color]
    elif color_mode == 'hybrid':
        svg_doc, stats, palette = trace_hybrid(
            image_input=image_input,
            kept_indices=kept_indices,
            monochrome_color=monochrome_color,
            n_colors=n_colors,
            preset=preset,
            mode=mode,
            hierarchical=hierarchical,
            use_full_image=use_full_image,
            square_canvas=square_canvas,
            bg_color=bg_color,
            custom_params=custom_params
        )
    elif color_mode in ('full', 'color'):
        svg_doc, stats, palette = trace_full_color(
            image_input=image_input,
            n_colors=n_colors,
            preset=preset,
            mode=mode,
            hierarchical=hierarchical,
            use_full_image=use_full_image,
            square_canvas=square_canvas,
            bg_color=bg_color,
            custom_params=custom_params
        )
    else:
        raise SvgTracingError(f"Unsupported color mode: {color_mode}")

    # Optional server-side recoloring / near-white pruning
    if palette_map or remove_near_white:
        recolor_map = palette_map or {}
        svg_doc, stats = apply_palette_recoloring(
            svg_doc,
            palette_map=recolor_map,
            remove_near_white=remove_near_white
        )

    return svg_doc, stats, palette
