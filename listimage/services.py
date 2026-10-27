"""
ListImage Core Image Processing Services.
All image manipulation, rembg model execution, alpha matting, touch-up,
connected-component object labeling, and canvas centering live here.
"""

import gc
import io
import json
import logging
import math
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps
import scipy.ndimage
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    pillow_heif = None
    HEIF_SUPPORTED = False

logger = logging.getLogger(__name__)
if not HEIF_SUPPORTED:
    logger.info("pillow_heif not installed; HEIC format will not be supported until pillow-heif is installed.")

# Constants
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_MEGAPIXELS = 60_000_000          # 60 Megapixels
CANVAS_SIZE = 2000                   # Target pure white square: 2000x2000 px
PADDING_PX = 10                      # Exact 10 px padding on constraining side
MAX_OBJECT_DIM = CANVAS_SIZE - (2 * PADDING_PX)  # 1980x1980 px
INFERENCE_MAX_DIM = 2048             # Downscale for rembg inference on huge images

# Singleton rembg session cache
_SESSIONS_LOCK = threading.Lock()
_SESSIONS_CACHE: Dict[str, Any] = {}

AVAILABLE_MODELS = {
    'isnet-general-use': 'IS-Net General Use (Default, balanced)',
    'birefnet-general': 'BiRefNet General (Highest quality edges)',
    'u2netp': 'U2Net+ (Fast, lightweight)',
}


class ImageProcessingError(Exception):
    """Base exception for image processing errors."""
    pass


class ValidationError(ImageProcessingError):
    """Raised when an uploaded file fails integrity, format, or size checks."""
    pass


def get_rembg_session(model_name: str = 'isnet-general-use'):
    """
    Returns a thread-safe cached rembg session for the requested model.
    Loads models once to avoid repeated disk reads and onnx initialization overhead.
    """
    import rembg
    if model_name not in AVAILABLE_MODELS:
        model_name = 'isnet-general-use'

    with _SESSIONS_LOCK:
        if model_name not in _SESSIONS_CACHE:
            logger.info("Initializing rembg session for model: %s", model_name)
            try:
                _SESSIONS_CACHE[model_name] = rembg.new_session(model_name)
            except Exception as e:
                logger.warning("Failed to initialize model %s, falling back to u2netp or default: %s", model_name, e)
                try:
                    _SESSIONS_CACHE[model_name] = rembg.new_session('u2netp')
                except Exception as e2:
                    logger.error("Failed to initialize fallback rembg session: %s", e2)
                    raise ImageProcessingError(f"Could not load AI background removal model: {e2}") from e2
        return _SESSIONS_CACHE[model_name]


def validate_and_normalize_upload(uploaded_file, workspace_dir: Path) -> Tuple[Path, Tuple[int, int]]:
    """
    Validates uploaded file:
    - Size <= 25MB
    - Valid image decoded by Pillow
    - Max 60 megapixels
    - Reject animated files (GIF, animated WebP, APNG)
    - EXIF transposition
    - Convert to sRGB RGB or RGBA, flattening CMYK/palette cleanly
    - Saves normalized PNG to workspace_dir / 'original.png'
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Size check
    file_size = getattr(uploaded_file, 'size', None)
    if file_size is None:
        try:
            uploaded_file.seek(0, io.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)
        except Exception:
            file_size = 0

    if file_size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"File size ({file_size / (1024*1024):.1f} MB) exceeds maximum allowed 25 MB.")

    try:
        img = Image.open(uploaded_file)
    except Exception as e:
        raise ValidationError(f"Invalid or corrupted image file: {e}") from e

    # Reject animated files
    if getattr(img, 'is_animated', False) or getattr(img, 'n_frames', 1) > 1:
        raise ValidationError("Animated images (GIF/APNG/Animated WebP) are not supported. Please upload a static image.")

    w, h = img.size
    total_pixels = w * h
    if total_pixels > MAX_MEGAPIXELS:
        raise ValidationError(f"Image resolution ({w}x{h} = {total_pixels/1e6:.1f} MP) exceeds 60 Megapixel limit.")

    # EXIF-transpose to honor orientation metadata
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Normalize color space to sRGB RGBA
    if img.mode in ('RGBA', 'LA'):
        normalized = img.convert('RGBA')
    elif img.mode == 'P':
        # Palette image with transparency check
        if 'transparency' in img.info:
            normalized = img.convert('RGBA')
        else:
            normalized = img.convert('RGB').convert('RGBA')
    elif img.mode == 'CMYK':
        # Convert CMYK to RGB accurately
        normalized = img.convert('RGB').convert('RGBA')
    else:
        normalized = img.convert('RGB').convert('RGBA')

    original_path = workspace_dir / 'original.png'
    normalized.save(original_path, format='PNG', optimize=False)

    final_size = normalized.size
    del normalized
    del img
    gc.collect()

    return original_path, final_size


def remove_background_with_rembg(
    input_image: Image.Image,
    model_name: str = 'isnet-general-use',
    alpha_matting: bool = False,
    edge_smoothing: bool = False,
) -> Image.Image:
    """
    Executes rembg background removal with memory-efficient downscaling fallback
    for ultra-large images. Preserves full-resolution RGB while applying the generated alpha mask.
    """
    import rembg

    session = get_rembg_session(model_name)
    w, h = input_image.size
    max_dim = max(w, h)

    # If the image is very large, downscale a copy for model inference to prevent OOM
    if max_dim > INFERENCE_MAX_DIM:
        scale = INFERENCE_MAX_DIM / float(max_dim)
        downscaled_w = max(1, int(round(w * scale)))
        downscaled_h = max(1, int(round(h * scale)))

        # Downscale copy for inference
        inference_input = input_image.resize((downscaled_w, downscaled_h), Image.Resampling.BILINEAR)

        # Run rembg returning mask only
        mask_out = rembg.remove(
            inference_input,
            session=session,
            only_mask=True,
            alpha_matting=alpha_matting,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
        if isinstance(mask_out, Image.Image):
            small_mask = mask_out.convert('L')
        elif isinstance(mask_out, np.ndarray):
            small_mask = Image.fromarray(mask_out).convert('L')
        else:
            small_mask = Image.open(io.BytesIO(mask_out)).convert('L')

        # Scale mask back to full resolution
        full_mask = small_mask.resize((w, h), Image.Resampling.LANCZOS)
        del small_mask
        del inference_input
    else:
        # Direct inference at native resolution
        cutout_out = rembg.remove(
            input_image,
            session=session,
            alpha_matting=alpha_matting,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
        if isinstance(cutout_out, Image.Image):
            native_cutout = cutout_out.convert('RGBA')
        elif isinstance(cutout_out, np.ndarray):
            native_cutout = Image.fromarray(cutout_out).convert('RGBA')
        else:
            native_cutout = Image.open(io.BytesIO(cutout_out)).convert('RGBA')

        full_mask = native_cutout.split()[3]
        del native_cutout

    # Optional edge smoothing via slight Gaussian blur on the mask
    if edge_smoothing:
        full_mask = full_mask.filter(ImageFilter.GaussianBlur(radius=0.75))

    # Apply alpha mask to the original full-resolution image
    result = input_image.copy().convert('RGBA')
    result.putalpha(full_mask)

    del full_mask
    gc.collect()
    return result


def detect_connected_objects(
    alpha_channel: Image.Image,
    min_area_threshold: int = 150
) -> Tuple[np.ndarray, List[Dict[str, Any]], Image.Image]:
    """
    Identifies connected foreground components using scipy.ndimage.label.
    Cleans up noise specks smaller than min_area_threshold from the alpha channel.
    Returns:
    - labeled_mask: 2D numpy array of integer labels
    - object_meta: list of object metadata dicts sorted by area descending
    - cleaned_alpha: Image.Image with tiny noise specks eliminated
    """
    alpha_np = np.array(alpha_channel, dtype=np.uint8)
    binary = alpha_np > 25

    # 8-connectivity structure
    structure = np.ones((3, 3), dtype=int)
    labeled, num_features = scipy.ndimage.label(binary, structure=structure)

    if num_features == 0:
        return labeled, [], alpha_channel

    # Calculate object sizes
    sizes = scipy.ndimage.sum(binary, labeled, range(1, num_features + 1))
    if not isinstance(sizes, np.ndarray):
        sizes = np.array([sizes])

    objects = []
    # Total foreground area
    total_fg = float(np.sum(binary))

    object_slices = scipy.ndimage.find_objects(labeled)
    speck_labels = []

    for idx, area in enumerate(sizes, start=1):
        if area < min_area_threshold:
            speck_labels.append(idx)
            labeled[labeled == idx] = 0
            continue

        # Get bounding box slice from object_slices
        sl = object_slices[idx - 1] if (idx - 1 < len(object_slices)) else None
        if sl is None:
            continue
        sy, sx = sl
        bbox = [int(sx.start), int(sy.start), int(sx.stop), int(sy.stop)]

        objects.append({
            'id': idx,
            'area': int(area),
            'bbox': bbox,
            'area_ratio': round(float(area) / max(total_fg, 1.0), 4),
            'is_largest': False,
            'active': True,
        })

    # Zero out trivial noise specks completely from alpha_np to prevent stray noise flecks
    if speck_labels:
        speck_mask = np.isin(labeled, speck_labels)
        if np.any(speck_mask):
            dilated_speck = cv2.dilate(
                speck_mask.astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            ) > 0
            alpha_np[dilated_speck] = 0

    # Sort descending by area
    objects.sort(key=lambda o: o['area'], reverse=True)
    if objects:
        objects[0]['is_largest'] = True

    cleaned_alpha = Image.fromarray(alpha_np, mode='L')
    del alpha_np
    del binary
    return labeled, objects, cleaned_alpha


def apply_object_filter_to_mask(
    mask_np: np.ndarray,
    labeled_objects: np.ndarray,
    active_ids: Set[int],
    keep_all: bool = False
) -> np.ndarray:
    """
    Filters the alpha mask keeping only components in active_ids.
    If keep_all is True or active_ids contains all labels, retains all components.
    Cleanly eliminates excluded components and their semi-transparent feathering
    without leaving ghost outlines or halos.
    """
    filtered = mask_np.copy()
    if keep_all or not active_ids:
        return filtered

    active_ids_set = set(int(x) for x in active_ids)
    all_labels = set(np.unique(labeled_objects)) - {0}
    inactive_labels = all_labels - active_ids_set

    if not inactive_labels:
        return filtered

    # Core regions of active vs inactive objects
    keep_core = np.isin(labeled_objects, list(active_ids_set)) & (labeled_objects > 0)
    keep_protected = cv2.dilate(
        keep_core.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    ) > 0

    exclude_core = np.isin(labeled_objects, list(inactive_labels)) & (labeled_objects > 0)
    exclude_dilated = cv2.dilate(
        exclude_core.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    ) > 0

    # Zero out excluded regions that do not belong to active objects
    mask_to_zero = exclude_dilated & (~keep_protected)
    filtered[mask_to_zero] = 0

    return filtered


def auto_touchup_alpha(alpha_channel: Image.Image, guided_refine: bool = True) -> Image.Image:
    """
    Heuristic touch-up for transparent and reflective items (glass, jewelry, chrome):
    1. Hole filling inside foreground (scipy.ndimage.binary_fill_holes)
    2. Morphological closing to reconnect broken glass or thin metallic edges
    3. Removal of small floating fragments
    4. Guided-filter / feathered edge refinement via OpenCV
    """
    alpha_np = np.array(alpha_channel, dtype=np.uint8)
    h, w = alpha_np.shape

    # Binary mask
    binary = alpha_np > 20

    # 1. Hole filling inside object (e.g. hollow areas of transparent cups, glasses, reflections)
    filled = scipy.ndimage.binary_fill_holes(binary)

    # 2. Morphological close to reconnect broken edges
    kernel_size = 5
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(filled.astype(np.uint8), cv2.MORPH_CLOSE, kernel)

    # 3. Remove small floating fragments
    labeled, num_features = scipy.ndimage.label(closed > 0)
    if num_features > 0:
        sizes = scipy.ndimage.sum(closed > 0, labeled, range(1, num_features + 1))
        if not isinstance(sizes, np.ndarray):
            sizes = np.array([sizes])
        max_area = float(np.max(sizes)) if len(sizes) > 0 else 0
        min_keep_area = max(200, max_area * 0.01)  # Drop specks smaller than 1% of largest object

        for idx, area in enumerate(sizes, start=1):
            if area < min_keep_area:
                closed[labeled == idx] = 0

    # 4. Guided feathered edge refinement using OpenCV
    if guided_refine:
        # Smooth mask with subtle feathering to restore natural optical edges
        smoothed = cv2.GaussianBlur(closed.astype(np.float32) * 255.0, (5, 5), sigmaX=1.2)
        # Blend original alpha details with smoothed filled mask
        # Preserve original interior gradients where alpha was semi-transparent
        touchup_alpha = np.where(closed > 0, np.maximum(alpha_np, smoothed.astype(np.uint8)), 0)
    else:
        touchup_alpha = (closed * 255).astype(np.uint8)

    del alpha_np
    del binary
    del filled
    del closed
    gc.collect()

    return Image.fromarray(touchup_alpha, mode='L')


def apply_magic_wand_color_key(
    rgba_img: Image.Image,
    seed_points: List[Tuple[int, int]],
    tolerance: int = 30
) -> Image.Image:
    """
    Magic-wand / color-key background remover for flat or solid backgrounds.
    Performs flood-fill or Euclidean RGB distance removal from seed coordinates.
    """
    img_np = np.array(rgba_img)
    rgb = img_np[:, :, :3].astype(np.int32)
    alpha = img_np[:, :, 3].copy()
    h, w, _ = img_np.shape

    # For each seed point, flood-fill similar colors
    mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    for sx, sy in seed_points:
        if 0 <= sx < w and 0 <= sy < h:
            cv2.floodFill(
                img_np[:, :, :3],
                mask,
                seedPoint=(sx, sy),
                newVal=(0, 0, 0),
                loDiff=(tolerance, tolerance, tolerance),
                upDiff=(tolerance, tolerance, tolerance),
                flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY
            )

    # Mask filled areas in alpha channel
    filled_area = mask[1:h+1, 1:w+1] > 0
    alpha[filled_area] = 0

    img_np[:, :, 3] = alpha
    result = Image.fromarray(img_np, mode='RGBA')

    del img_np
    del rgb
    del alpha
    del mask
    gc.collect()

    return result


def render_to_pure_white_canvas(
    rgba_img: Image.Image,
    target_size: int = CANVAS_SIZE,
    padding: int = PADDING_PX,
    nudge_x: int = 0,
    nudge_y: int = 0,
    zoom: float = 1.0,
) -> Tuple[Image.Image, Image.Image, Dict[str, Any]]:
    """
    Centers the subject(s) on a 2000x2000 px square:
    1. Tightly crops to the bounding box containing all active subjects.
    2. Uniformly scales (never stretches) to fit inside (target_size - 2*padding) = 1980x1980.
       - Downscaling: Lanczos.
       - Upscaling: Lanczos on premultiplied alpha (to eliminate dark halos) + light unsharp mask.
    3. Centers using integer-exact math. The constraining side has EXACTLY 10 px padding.
    4. Produces both pure white canvas (RGB) and transparent canvas (RGBA).
    """
    bbox = rgba_img.getbbox()
    if not bbox:
        # Fully transparent image: return blank white and transparent canvas
        blank = Image.new('RGB', (target_size, target_size), (255, 255, 255))
        blank_trans = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
        return blank, blank_trans, {
            'scaled_w': 0, 'scaled_h': 0,
            'offset_x': padding, 'offset_y': padding,
            'pad_left': padding, 'pad_right': padding,
            'pad_top': padding, 'pad_bottom': padding,
            'constraining_side': 'none',
            'is_upscaled': False,
        }

    cropped = rgba_img.crop(bbox)
    crop_w, crop_h = cropped.size
    max_bound = target_size - (2 * padding)  # 1980 px

    # Compute uniform scaling factor so constraining side equals exactly max_bound (1980 px)
    scale_x = max_bound / float(crop_w)
    scale_y = max_bound / float(crop_h)

    if scale_x <= scale_y:
        # Width is constraining
        base_scale = scale_x
        constraining_side = 'width'
    else:
        # Height is constraining
        base_scale = scale_y
        constraining_side = 'height'

    scale = base_scale * zoom
    scaled_w = max(1, int(round(crop_w * scale)))
    scaled_h = max(1, int(round(crop_h * scale)))

    # If zoom <= 1.0, clamp precisely to max_bound on the constraining side
    if zoom <= 1.0:
        if constraining_side == 'width':
            scaled_w = max_bound
            scaled_h = min(max_bound, max(1, int(round(crop_h * (max_bound / float(crop_w))))))
        else:
            scaled_h = max_bound
            scaled_w = min(max_bound, max(1, int(round(crop_w * (max_bound / float(crop_h))))))

    is_upscale = (scaled_w > crop_w) or (scaled_h > crop_h)

    # Perform scaling
    if is_upscale:
        # Upscale using premultiplied alpha to prevent dark edge fringing/halos
        r, g, b, a = cropped.split()
        a_arr = np.array(a, dtype=np.float32) / 255.0
        rgb_arr = np.array(cropped.convert('RGB'), dtype=np.float32)

        # Premultiply RGB by Alpha
        rgb_prem = (rgb_arr * a_arr[..., None]).astype(np.uint8)
        prem_img = Image.fromarray(rgb_prem, mode='RGB')

        # Resize RGB and Alpha separately with Lanczos
        scaled_rgb_prem = prem_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        scaled_a = a.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Un-premultiply
        scaled_a_arr = np.array(scaled_a, dtype=np.float32) / 255.0
        scaled_rgb_arr = np.array(scaled_rgb_prem, dtype=np.float32)

        unprem = np.zeros_like(scaled_rgb_arr)
        nonzero = scaled_a_arr > 1e-4
        unprem[nonzero] = np.clip(scaled_rgb_arr[nonzero] / scaled_a_arr[nonzero, None], 0, 255)

        scaled_img = Image.fromarray(unprem.astype(np.uint8), mode='RGB')
        scaled_img.putalpha(scaled_a)

        # Light unsharp mask on upscale only
        scaled_img = scaled_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=3))

        del a_arr, rgb_arr, rgb_prem, prem_img, scaled_rgb_prem, scaled_a, scaled_a_arr, scaled_rgb_arr, unprem
    else:
        # Downscale large images with standard Lanczos
        scaled_img = cropped.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Center on 2000x2000 pure white canvas using exact integer division
    base_offset_x = (target_size - scaled_w) // 2
    base_offset_y = (target_size - scaled_h) // 2

    final_offset_x = base_offset_x + nudge_x
    final_offset_y = base_offset_y + nudge_y

    canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
    canvas.paste(scaled_img, (final_offset_x, final_offset_y), scaled_img.split()[3])

    canvas_trans = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
    canvas_trans.paste(scaled_img, (final_offset_x, final_offset_y), scaled_img.split()[3])

    # Calculate padding metrics
    pad_left = final_offset_x
    pad_right = target_size - (final_offset_x + scaled_w)
    pad_top = final_offset_y
    pad_bottom = target_size - (final_offset_y + scaled_h)

    metrics = {
        'scaled_w': scaled_w,
        'scaled_h': scaled_h,
        'offset_x': final_offset_x,
        'offset_y': final_offset_y,
        'pad_left': pad_left,
        'pad_right': pad_right,
        'pad_top': pad_top,
        'pad_bottom': pad_bottom,
        'constraining_side': constraining_side,
        'is_upscaled': is_upscale,
        'crop_bbox': list(bbox),
    }

    del cropped
    del scaled_img
    gc.collect()

    return canvas, canvas_trans, metrics


def check_white_edge_pixels(rgba_cutout: Image.Image) -> bool:
    """
    Checks if object edge pixels are very close to pure white (RGB > 240, 240, 240).
    Used to show a gentle warning in the UI:
    "Edges may be hard to see on white. Check the checker preview."
    """
    try:
        arr = np.array(rgba_cutout)
        alpha = arr[:, :, 3]
        # Dilate and erode alpha to locate edge contour
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate((alpha > 20).astype(np.uint8), kernel)
        eroded = cv2.erode((alpha > 20).astype(np.uint8), kernel)
        edge_mask = (dilated - eroded) > 0

        if not np.any(edge_mask):
            return False

        edge_rgb = arr[:, :, :3][edge_mask]
        # Check percentage of edge pixels with R, G, B all > 238
        near_white = np.all(edge_rgb > 238, axis=1)
        white_ratio = float(np.sum(near_white)) / float(len(near_white))
        return white_ratio > 0.15
    except Exception:
        return False


def process_initial_job(job_id: str, workspace_dir: Path, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full background processing pipeline for a new ImageJob:
    1. Loads normalized original.png
    2. Runs rembg background removal with selected model
    3. Identifies connected components and detects all main objects
    4. By default keeps ALL main foreground objects (matching PhotoRoom)
    5. Handles transparent/reflective mode if checked
    6. Stores full-resolution cutout.png and current_mask.png
    7. Renders final 2000x2000 pure white canvas & transparent canvas
    8. Writes metadata.json
    """
    original_path = workspace_dir / 'original.png'
    if not original_path.exists():
        raise FileNotFoundError(f"Original image not found in {workspace_dir}")

    original_img = Image.open(original_path).convert('RGBA')

    model_name = params.get('model', 'isnet-general-use')
    alpha_matting = bool(params.get('alpha_matting', False))
    edge_smoothing = bool(params.get('edge_smoothing', False))
    keep_largest = bool(params.get('keep_largest', False))
    transparent_mode = bool(params.get('transparent_mode', False))

    logger.info("Starting background removal for job %s with model=%s, keep_largest=%s", job_id, model_name, keep_largest)

    # 1. Background removal
    cutout = remove_background_with_rembg(
        original_img,
        model_name=model_name,
        alpha_matting=alpha_matting,
        edge_smoothing=edge_smoothing,
    )

    alpha_channel = cutout.split()[3]

    # 2. Object detection
    labeled_array, detected_objects, alpha_channel = detect_connected_objects(alpha_channel)
    cutout.putalpha(alpha_channel)

    # 3. Transparent / reflective touch-up if mode selected
    if transparent_mode:
        alpha_channel = auto_touchup_alpha(alpha_channel)
        cutout.putalpha(alpha_channel)
        # Re-detect objects on touched up alpha
        labeled_array, detected_objects, alpha_channel = detect_connected_objects(alpha_channel)

    # 4. Filter objects ONLY if keep_largest is explicitly enabled
    active_ids = set()
    if keep_largest and detected_objects:
        largest_obj = detected_objects[0]
        active_ids = {largest_obj['id']}
        for obj in detected_objects:
            obj['active'] = (obj['id'] == largest_obj['id'])

        alpha_np = np.array(alpha_channel, dtype=np.uint8)
        filtered_alpha = apply_object_filter_to_mask(alpha_np, labeled_array, active_ids, keep_all=False)
        alpha_channel = Image.fromarray(filtered_alpha, mode='L')
        cutout.putalpha(alpha_channel)
    else:
        # Keep ALL main objects by default (matching PhotoRoom)
        for obj in detected_objects:
            obj['active'] = True
            active_ids.add(obj['id'])

    # 5. Save full-resolution cutout and mask for non-destructive edits
    cutout_path = workspace_dir / 'cutout.png'
    mask_path = workspace_dir / 'current_mask.png'
    cutout.save(cutout_path, format='PNG')
    alpha_channel.save(mask_path, format='PNG')

    # 6. Render 2000x2000 pure white canvas and transparent canvas
    canvas, canvas_trans, metrics = render_to_pure_white_canvas(cutout)
    rendered_path = workspace_dir / 'rendered_2000.png'
    rendered_trans_path = workspace_dir / 'rendered_transparent.png'
    canvas.save(rendered_path, format='PNG')
    canvas_trans.save(rendered_trans_path, format='PNG')

    # 7. Check white-on-white edge warning
    warn_white_edges = check_white_edge_pixels(cutout)

    # 8. Consolidate params & metadata
    updated_params = {
        'model': model_name,
        'alpha_matting': alpha_matting,
        'edge_smoothing': edge_smoothing,
        'keep_largest': keep_largest,
        'transparent_mode': transparent_mode,
        'active_objects': list(active_ids),
        'detected_objects': detected_objects,
        'metrics': metrics,
        'warn_white_edges': warn_white_edges,
        'nudge_x': 0,
        'nudge_y': 0,
        'zoom': 1.0,
        'touchup_applied': transparent_mode,
    }

    meta_file = workspace_dir / 'meta.json'
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(updated_params, f, indent=2)

    del original_img
    del cutout
    del alpha_channel
    del canvas
    gc.collect()

    return updated_params


def apply_edits_and_rerender(
    workspace_dir: Path,
    edits: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Applies non-destructive amendments to the full-resolution cutout:
    - Object selection / exclusion
    - Erase/restore brush mask strokes or wand cuts
    - Auto touch-up toggle
    - Nudge and zoom adjustments
    - Re-renders to rendered_2000.png
    """
    cutout_path = workspace_dir / 'cutout.png'
    original_path = workspace_dir / 'original.png'
    mask_path = workspace_dir / 'current_mask.png'
    meta_path = workspace_dir / 'meta.json'

    if not cutout_path.exists():
        raise FileNotFoundError(f"Cutout image not found in {workspace_dir}")

    # Read previous metadata
    current_meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                current_meta = json.load(f)
        except Exception:
            pass

    # Merge edits into params
    model_name = edits.get('model', current_meta.get('model', 'isnet-general-use'))
    keep_largest = edits.get('keep_largest', current_meta.get('keep_largest', False))
    nudge_x = int(edits.get('nudge_x', current_meta.get('nudge_x', 0)))
    nudge_y = int(edits.get('nudge_y', current_meta.get('nudge_y', 0)))
    zoom = float(edits.get('zoom', current_meta.get('zoom', 1.0)))
    zoom = max(0.5, min(1.0, zoom))  # Constrained between 0.5 and 1.0 to respect padding limit

    # Check if model re-processing was requested
    if edits.get('reprocess_model'):
        logger.info("Re-processing model with %s for %s", model_name, workspace_dir)
        return process_initial_job(
            job_id=workspace_dir.name,
            workspace_dir=workspace_dir,
            params={**current_meta, **edits, 'model': model_name}
        )

    # Load full-resolution cutout
    cutout = Image.open(cutout_path).convert('RGBA')
    w, h = cutout.size

    # Load current alpha mask or extract from cutout
    if mask_path.exists():
        alpha_mask = Image.open(mask_path).convert('L')
    else:
        alpha_mask = cutout.split()[3]

    # Handle incoming mask edits (e.g., base64 mask overlay from brush/wand)
    mask_data_b64 = edits.get('mask_delta_b64')
    if mask_data_b64:
        import base64
        try:
            if ',' in mask_data_b64:
                mask_data_b64 = mask_data_b64.split(',', 1)[1]
            delta_bytes = base64.b64decode(mask_data_b64)
            delta_img = Image.open(io.BytesIO(delta_bytes)).convert('RGBA')
            if delta_img.size != (w, h):
                delta_img = delta_img.resize((w, h), Image.Resampling.NEAREST)

            # Red channel = restore, Blue/Alpha = erase
            delta_np = np.array(delta_img)
            mask_np = np.array(alpha_mask)

            # Where delta has erase (e.g. green or alpha with erase flag)
            erase_mode = edits.get('brush_mode') == 'erase'
            brush_pixels = delta_np[:, :, 3] > 10

            if erase_mode:
                mask_np[brush_pixels] = 0
            else:
                # Restore: restore original alpha from original or set to 255
                mask_np[brush_pixels] = 255

            alpha_mask = Image.fromarray(mask_np, mode='L')
            alpha_mask.save(mask_path, format='PNG')
        except Exception as e:
            logger.error("Failed to apply mask delta: %s", e)

    # Handle active objects toggle
    active_objects = edits.get('active_objects')
    detected_objects = current_meta.get('detected_objects', [])
    if active_objects is not None and detected_objects:
        active_set = set(int(x) for x in active_objects)
        labeled_array, _, alpha_mask = detect_connected_objects(alpha_mask)
        mask_np = np.array(alpha_mask)
        filtered_np = apply_object_filter_to_mask(mask_np, labeled_array, active_set, keep_all=False)
        alpha_mask = Image.fromarray(filtered_np, mode='L')
        alpha_mask.save(mask_path, format='PNG')

        for obj in detected_objects:
            obj['active'] = (obj['id'] in active_set)

    # Apply alpha back to cutout
    cutout.putalpha(alpha_mask)

    # Render to 2000x2000 pure white canvas and transparent canvas
    canvas, canvas_trans, metrics = render_to_pure_white_canvas(
        cutout,
        nudge_x=nudge_x,
        nudge_y=nudge_y,
        zoom=zoom,
    )
    rendered_path = workspace_dir / 'rendered_2000.png'
    rendered_trans_path = workspace_dir / 'rendered_transparent.png'
    canvas.save(rendered_path, format='PNG')
    canvas_trans.save(rendered_trans_path, format='PNG')

    warn_white_edges = check_white_edge_pixels(cutout)

    updated_meta = {
        **current_meta,
        'nudge_x': nudge_x,
        'nudge_y': nudge_y,
        'zoom': zoom,
        'metrics': metrics,
        'warn_white_edges': warn_white_edges,
        'detected_objects': detected_objects,
        'active_objects': list(active_objects) if active_objects is not None else current_meta.get('active_objects', []),
    }

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(updated_meta, f, indent=2)

    del cutout
    del alpha_mask
    del canvas
    del canvas_trans
    gc.collect()

    return updated_meta


def apply_touchup_to_workspace(workspace_dir: Path, enable: bool = True) -> Dict[str, Any]:
    """
    Toggles auto touch-up on the current workspace cutout.
    Saves before/after so touchup can be undone non-destructively.
    """
    cutout_path = workspace_dir / 'cutout.png'
    mask_path = workspace_dir / 'current_mask.png'
    meta_path = workspace_dir / 'meta.json'
    pre_touchup_mask = workspace_dir / 'pre_touchup_mask.png'

    if not cutout_path.exists():
        raise FileNotFoundError("Cutout file does not exist.")

    cutout = Image.open(cutout_path).convert('RGBA')

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    if enable:
        # Save pre-touchup mask for undo
        if mask_path.exists() and not pre_touchup_mask.exists():
            shutil.copyfile(mask_path, pre_touchup_mask)

        current_alpha = Image.open(mask_path).convert('L') if mask_path.exists() else cutout.split()[3]
        touched_alpha = auto_touchup_alpha(current_alpha)
        touched_alpha.save(mask_path, format='PNG')
        cutout.putalpha(touched_alpha)
        meta['touchup_applied'] = True
    else:
        # Undo touchup
        if pre_touchup_mask.exists():
            shutil.copyfile(pre_touchup_mask, mask_path)
            restored_alpha = Image.open(pre_touchup_mask).convert('L')
            cutout.putalpha(restored_alpha)
        meta['touchup_applied'] = False

    # Re-render 2000x2000 canvas
    canvas, canvas_trans, metrics = render_to_pure_white_canvas(
        cutout,
        nudge_x=meta.get('nudge_x', 0),
        nudge_y=meta.get('nudge_y', 0),
        zoom=meta.get('zoom', 1.0)
    )
    canvas.save(workspace_dir / 'rendered_2000.png', format='PNG')
    canvas_trans.save(workspace_dir / 'rendered_transparent.png', format='PNG')
    meta['metrics'] = metrics

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    del cutout
    del canvas
    del canvas_trans
    gc.collect()

    return meta


def export_rendered_image(workspace_dir: Path, format: str = 'PNG') -> io.BytesIO:
    """
    Generates downloadable image buffer:
    - PNG / PNG_WHITE: Lossless pure white 2000x2000 PNG
    - PNG_TRANSPARENT: Lossless transparent 2000x2000 PNG (cutout)
    - JPEG / JPG: Quality 95, 4:4:4 chroma subsampling, sRGB pure white
    """
    fmt = format.upper()
    buffer = io.BytesIO()

    if fmt in ('PNG_TRANSPARENT', 'TRANSPARENT'):
        trans_path = workspace_dir / 'rendered_transparent.png'
        if not trans_path.exists():
            trans_path = workspace_dir / 'cutout.png'
        if not trans_path.exists():
            raise FileNotFoundError(f"Transparent image not found in {workspace_dir}")
        img = Image.open(trans_path).convert('RGBA')
        img.save(buffer, format='PNG', optimize=True)
    elif fmt in ('JPG', 'JPEG'):
        rendered_path = workspace_dir / 'rendered_2000.png'
        if not rendered_path.exists():
            raise FileNotFoundError(f"Rendered image not found at {rendered_path}")
        img = Image.open(rendered_path).convert('RGB')
        img.save(
            buffer,
            format='JPEG',
            quality=95,
            subsampling=0,
            optimize=True
        )
    else:
        # Default pure white PNG
        rendered_path = workspace_dir / 'rendered_2000.png'
        if not rendered_path.exists():
            raise FileNotFoundError(f"Rendered image not found at {rendered_path}")
        img = Image.open(rendered_path).convert('RGB')
        img.save(buffer, format='PNG', optimize=True)

    buffer.seek(0)
    del img
    gc.collect()
    return buffer
