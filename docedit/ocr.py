"""
OCR engine for scanned old books and fuzzy historical documents.

Tailored for aged, yellowed, stained paper and fuzzy faded ink:
- Pre-processing pipelines: raw grayscale, grayscale + contrast/denoise (best for LSTM), binarized
- Projection-profile deskew and optional dewarp/page-curl correction
- 300 DPI equivalent upscaling before Tesseract OCR
- Multi-lingual Tesseract with word-level bounding boxes, confidence, and line/block metrics
- Detection of low-confidence and suspicious character combinations for the review queue
- Confidence heatmap tagging (low < 60, amber 60-80, high >= 80)
- Supports English, Hindi, Gujarati, Arabic, and automatic language downloading
"""
import html
import io
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from .conf import conf
from .security import validate_ocr_lang

logger = logging.getLogger(__name__)

_AVAILABLE_LANGS_CACHE: Optional[List[str]] = None


def get_tesseract_cmd() -> str:
    cmd = conf.TESSERACT_CMD
    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


def get_available_ocr_languages(force_refresh: bool = False) -> List[str]:
    """Returns list of language codes installed in Tesseract (cached)."""
    global _AVAILABLE_LANGS_CACHE
    if _AVAILABLE_LANGS_CACHE is not None and not force_refresh:
        return _AVAILABLE_LANGS_CACHE
    try:
        get_tesseract_cmd()
        langs = pytesseract.get_languages(config="")
        _AVAILABLE_LANGS_CACHE = [l for l in langs if l != "osd"]
        return _AVAILABLE_LANGS_CACHE
    except Exception as e:
        logger.warning("Could not list tesseract languages: %s", e)
        return ["eng"]


def ensure_ocr_language(lang: str) -> bool:
    """
    Checks if a language is installed; if not and downloads allowed, downloads it.
    Prefers tessdata_best models when configured.
    Validates language code to prevent path traversal.
    """
    try:
        lang = validate_ocr_lang(lang)
    except ValueError as e:
        logger.warning("Rejected invalid OCR language '%s': %s", lang, e)
        return False

    langs = get_available_ocr_languages()
    if lang in langs:
        return True
    if not conf.ALLOW_DOWNLOADS:
        return False

    # Find tessdata dir
    tess_cmd = Path(get_tesseract_cmd())
    tessdata_dir = tess_cmd.parent / "tessdata"
    if not tessdata_dir.is_dir():
        logger.warning("tessdata dir not found at %s", tessdata_dir)
        return False

    target_file = (tessdata_dir / f"{lang}.traineddata").resolve()
    # Path traversal safeguard
    if not str(target_file).startswith(str(tessdata_dir.resolve())):
        logger.warning("Path traversal attempt in OCR language pack: %s", target_file)
        return False

    url = conf.TESSDATA_URL.format(lang=lang)
    try:
        logger.info("Downloading OCR language pack %s (%s) from %s", lang, conf.TESSDATA_MODEL_SET, url)
        req = urllib.request.Request(url, headers={"User-Agent": "project-h-docedit/1.0"})
        with urllib.request.urlopen(req, timeout=conf.HTTP_TIMEOUT * 2) as resp:
            target_file.write_bytes(resp.read())
        # Invalidate cache so newly downloaded language is detected
        get_available_ocr_languages(force_refresh=True)
        return True
    except Exception as e:
        logger.warning("Failed downloading OCR language pack %s: %s", lang, e)
        return False


# ============================================================================
# Preprocessing: Deskew, Dewarp, Upscaling, and Profiles
# ============================================================================

def compute_skew_angle(img: Image.Image, max_angle: float = 10.0, step: float = 0.5) -> float:
    """
    Calculates the page rotation/skew angle using horizontal projection profile variance.
    When lines of text are horizontally aligned, row sums of pixel intensity produce
    extreme peaks (text baselines) and valleys (leading spaces), maximizing variance.
    """
    gray = img.convert("L") if img.mode != "L" else img
    target_w = 600
    if gray.width > target_w:
        aspect = gray.height / gray.width
        small = gray.resize((target_w, max(10, int(target_w * aspect))), Image.Resampling.BILINEAR)
    else:
        small = gray.copy()

    # Coarse pass across [-max_angle, max_angle]
    coarse_angles = np.arange(-max_angle, max_angle + step, step)
    best_angle = 0.0
    max_var = -1.0

    for a in coarse_angles:
        rot = small.rotate(float(a), resample=Image.Resampling.BILINEAR, fillcolor=255)
        arr = np.array(rot)
        row_sums = np.sum(255.0 - arr, axis=1)
        v = float(np.var(row_sums))
        if v > max_var:
            max_var = v
            best_angle = float(a)

    # Fine pass around best_angle (+-0.5 degrees at 0.1 deg step)
    fine_angles = np.arange(best_angle - 0.5, best_angle + 0.6, 0.1)
    for a in fine_angles:
        rot = small.rotate(float(a), resample=Image.Resampling.BILINEAR, fillcolor=255)
        arr = np.array(rot)
        row_sums = np.sum(255.0 - arr, axis=1)
        v = float(np.var(row_sums))
        if v > max_var:
            max_var = v
            best_angle = float(a)

    # Ignore tiny sub-0.2 degree variations to prevent unnecessary resampling blur
    if abs(best_angle) < 0.2:
        return 0.0

    return round(float(best_angle), 2)


def deskew_image(img: Image.Image, angle: Optional[float] = None) -> Tuple[Image.Image, float]:
    """
    Detects and corrects skew angle.
    Returns (deskewed_image, applied_angle_degrees).
    """
    if angle is None:
        angle = compute_skew_angle(img)

    if abs(angle) < 0.2:
        return img, 0.0

    fill = (255, 255, 255) if img.mode in ("RGB", "RGBA") else 255
    deskewed = img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=fill)
    return deskewed, angle


def dewarp_page_curl(img: Image.Image, max_displacement: float = 12.0) -> Image.Image:
    """
    Optional dewarp/page-curl correction for bound book scans.
    Models spine curvature along vertical column strips and applies bilinear mesh mapping.
    """
    w, h = img.size
    if w < 100 or h < 100:
        return img

    num_cols = 16
    col_w = w / num_cols
    mesh = []

    # Book spine curl decays exponentially from the inner spine margin
    decay_width = max(100.0, w * 0.25)
    for i in range(num_cols):
        x0 = int(round(i * col_w))
        x1 = int(round((i + 1) * col_w))

        dy0 = max_displacement * np.exp(-x0 / decay_width)
        dy1 = max_displacement * np.exp(-x1 / decay_width)

        src_quad = (
            x0, 0 + dy0,
            x0, h + dy0,
            x1, h + dy1,
            x1, 0 + dy1,
        )
        target_box = (x0, 0, x1, h)
        mesh.append((target_box, src_quad))

    fill = (255, 255, 255) if img.mode in ("RGB", "RGBA") else 255
    return img.transform(
        (w, h),
        Image.Transform.MESH,
        mesh,
        resample=Image.Resampling.BILINEAR,
        fillcolor=fill
    )


def ensure_300_dpi_equivalent(img: Image.Image, dpi: int = 300) -> Tuple[Image.Image, float]:
    """
    Upscales images with low DPI / resolution to ~300 DPI equivalent before OCR.
    Tesseract's LSTM neural net yields significantly higher accuracy when character
    x-height is at least 25-30 pixels (standard ~300 DPI resolution).
    Returns (upscaled_image, scale_factor).
    """
    effective_dpi = float(dpi) if dpi and dpi > 30 else 300.0

    # If image dimensions are small (e.g. width < 1800 px for an A4 page), infer lower DPI
    if effective_dpi >= 280 and img.width < 1400:
        inferred = (img.width / 8.27)
        if 72 <= inferred < 250:
            effective_dpi = inferred

    if effective_dpi < 280:
        scale_factor = round(300.0 / effective_dpi, 3)
        scale_factor = max(1.0, min(scale_factor, 4.0))
    else:
        scale_factor = 1.0

    if scale_factor > 1.05:
        new_w = int(round(img.width * scale_factor))
        new_h = int(round(img.height * scale_factor))
        upscaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        return upscaled, scale_factor

    return img, 1.0


# ----------------------------------------------------------------------------
# 3 Preprocessing Pipelines for A/B Testing & Production
# ----------------------------------------------------------------------------

def preprocess_raw_grayscale(img: Image.Image) -> Image.Image:
    """Pipeline (a): Raw Grayscale conversion without contrast enhancement."""
    return img.convert("L") if img.mode != "L" else img.copy()


def preprocess_grayscale_contrast(img: Image.Image) -> Image.Image:
    """
    Pipeline (b): Grayscale + Contrast/Denoise (Optimal for Tesseract LSTM).
    1. Grayscale conversion.
    2. Autocontrast (1% cutoff) to remove aged/yellowed paper background.
    3. Contrast enhancement (1.35x) to darken faded historical ink.
    4. Unsharp mask (radius 1.2, 120%) to crisp character edges without haloing.
    5. Median denoise filter to suppress paper speckles and foxing spots.
    Preserves continuous stroke gradients needed by LSTM neural networks.
    """
    gray = img.convert("L") if img.mode != "L" else img.copy()
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.35)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray


def preprocess_binarized(img: Image.Image) -> Image.Image:
    """
    Pipeline (c): Binarized / High-Contrast pipeline via Otsu's thresholding.
    Separates foreground ink from background paper into strictly 0 or 255.
    """
    gray = img.convert("L") if img.mode != "L" else img.copy()
    gray = ImageOps.autocontrast(gray, cutoff=1)
    arr = np.array(gray)

    # Otsu's thresholding
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = np.dot(np.arange(256), hist)
    current_max = 0.0
    threshold = 128
    sum_b = 0.0
    w_b = 0

    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * ((m_b - m_f) ** 2)
        if var_between > current_max:
            current_max = var_between
            threshold = t

    bin_arr = np.where(arr > threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(bin_arr, mode="L")


def preprocess_old_book_image(img: Image.Image) -> Image.Image:
    """
    Backward-compatible entry point.
    Fixes dead code from earlier versions and routes to the optimized grayscale_contrast pipeline.
    """
    return preprocess_grayscale_contrast(img)


def preprocess_image(
    img: Image.Image,
    profile: Optional[str] = None,
    deskew: Optional[bool] = None,
    dewarp: Optional[bool] = None,
) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Unified pre-processing dispatcher:
    Applies deskew (if enabled), dewarp (if enabled), and the chosen profile.
    Returns (processed_image, metadata).
    """
    if profile is None:
        profile = getattr(conf, "OCR_PREPROCESS_PROFILE", "grayscale_contrast")
    if deskew is None:
        deskew = getattr(conf, "OCR_DESKEW", True)
    if dewarp is None:
        dewarp = getattr(conf, "OCR_DEWARP", False)

    cur = img
    skew_angle = 0.0
    if deskew:
        cur, skew_angle = deskew_image(cur)

    if dewarp:
        cur = dewarp_page_curl(cur)

    if profile == "raw_grayscale":
        processed = preprocess_raw_grayscale(cur)
    elif profile == "binarized":
        processed = preprocess_binarized(cur)
    else:
        profile = "grayscale_contrast"
        processed = preprocess_grayscale_contrast(cur)

    meta = {
        "profile": profile,
        "deskew_applied": deskew and abs(skew_angle) >= 0.2,
        "skew_angle": skew_angle,
        "dewarp_applied": dewarp,
    }
    return processed, meta


# ============================================================================
# Suspicious Character & Fuzzy Word Rules
# ============================================================================

_ORDINAL_RE = re.compile(r"^\d+(st|nd|rd|th)$", re.IGNORECASE)
_DIGIT_LETTER_MIX_RE = re.compile(r"[a-zA-Z]\d[a-zA-Z]|\d[a-zA-Z]\d|^[a-zA-Z]+\d+$|^\d+[a-zA-Z]+$")
_UNUSUAL_MID_PUNCT_RE = re.compile(r"[a-zA-Z0-9][~|^_+=/\\@#*<>{}\[\]][a-zA-Z0-9]")
_REPEATING_PUNCT_RE = re.compile(r"([.,:;!?\-~_=+*#])\1+")
_IRREGULAR_CASE_RE = re.compile(r"[a-z][A-Z][a-z]")
_ORPHAN_SYMBOLS = {"§", "©", "¢", "¦", "¤", "¥", "¶", "†", "‡"}


def detect_suspicious_word(
    text: str,
    conf_score: float,
    lang: str = "eng",
    threshold: Optional[float] = None,
) -> Tuple[bool, List[str]]:
    """
    Evaluates whether an OCR-recognized word should be flagged for the review queue.
    Combines confidence thresholding with linguistic/symbolic heuristics:
    - Low confidence score
    - Digits erroneously mixed into alphabetic words (e.g. th1s, b00k)
    - Strange interior punctuation (e.g. w~ord, t|ext)
    - Repetitive identical punctuation
    - Unbalanced quotes/brackets or stray noise glyphs
    - Irregular internal capitalization
    Returns (is_suspicious, reasons).
    """
    if threshold is None:
        threshold = float(getattr(conf, "OCR_LOW_CONFIDENCE", 70))

    reasons: List[str] = []

    # 1. Low confidence
    if conf_score < threshold:
        reasons.append(f"Low confidence ({round(conf_score, 1)}%)")

    clean_w = text.strip()
    if not clean_w:
        return bool(reasons), reasons

    # Skip heuristics on pure numbers or common ordinals
    if clean_w.isdigit() or _ORDINAL_RE.match(clean_w):
        return bool(reasons), reasons

    # 2. Mixed digits and letters inside word
    has_alpha = any(c.isalpha() for c in clean_w)
    has_digit = any(c.isdigit() for c in clean_w)
    if has_alpha and has_digit and not _ORDINAL_RE.match(clean_w):
        reasons.append("Suspicious mixed digits and letters")

    # 3. Unusual interior punctuation
    if _UNUSUAL_MID_PUNCT_RE.search(clean_w):
        reasons.append("Unusual punctuation inside word")

    # 4. Repeating punctuation
    if _REPEATING_PUNCT_RE.search(clean_w):
        reasons.append("Consecutive repeating punctuation")

    # 5. Orphan symbols or unclosed delimiters
    if any(s in clean_w for s in _ORPHAN_SYMBOLS):
        reasons.append("Contains orphan noise symbol")
    if (clean_w.startswith("(") and not clean_w.endswith(")")) or (clean_w.endswith(")") and not clean_w.startswith("(")):
        reasons.append("Unmatched parenthesis")
    if (clean_w.startswith("[") and not clean_w.endswith("]")) or (clean_w.endswith("]") and not clean_w.startswith("[")):
        reasons.append("Unmatched bracket")

    # 6. Irregular case mixing
    if _IRREGULAR_CASE_RE.search(clean_w):
        reasons.append("Irregular internal capitalization")

    is_fuzzy = len(reasons) > 0
    return is_fuzzy, reasons


# ============================================================================
# Main OCR Processing
# ============================================================================

def ocr_image(
    image: Image.Image,
    lang: str = "eng",
    dpi: int = 300,
    profile: Optional[str] = None,
    deskew: Optional[bool] = None,
    dewarp: Optional[bool] = None,
    psm: Optional[int] = None,
    page_num: int = 1,
) -> Dict[str, Any]:
    """
    Runs Tesseract OCR on a PIL image with full word-level data tracking.
    - Upscales to ~300 DPI equivalent before OCR
    - Applies deskew, optional dewarp, and preprocessing profile
    - Extracts per-word bounding box, confidence, block/line IDs
    - Maps bounding boxes back to original image coordinate space
    - Produces HTML representation with word spans and confidence tiers
    """
    get_tesseract_cmd()

    # Verify language or fallback
    available = get_available_ocr_languages()
    primary_lang = lang.split("+")[0]
    if primary_lang not in available:
        ensure_ocr_language(primary_lang)
        available = get_available_ocr_languages()

    valid_langs = [l for l in lang.split("+") if l in available]
    use_lang = "+".join(valid_langs) if valid_langs else "eng"

    # 1. Upscale to ~300 DPI equivalent
    upscaled_img, scale_factor = ensure_300_dpi_equivalent(image, dpi=dpi)

    # 2. Preprocess (deskew, dewarp, profile)
    clean_img, prep_meta = preprocess_image(
        upscaled_img,
        profile=profile,
        deskew=deskew,
        dewarp=dewarp,
    )

    chosen_psm = psm if psm is not None else getattr(conf, "OCR_PSM", 3)
    custom_config = f"--oem 1 --psm {chosen_psm} -c preserve_interword_spaces=1"

    try:
        data = pytesseract.image_to_data(
            clean_img,
            lang=use_lang,
            config=custom_config,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        logger.error("OCR execution failed: %s", e)
        try:
            txt = pytesseract.image_to_string(clean_img, lang=use_lang)
            return {
                "text": txt,
                "html": "".join(f"<p>{p.strip()}</p>" for p in txt.split("\n\n") if p.strip()),
                "words": [],
                "fuzzy_words": [],
                "line_boxes": [],
                "stats": {"word_count": len(txt.split()), "fuzzy_count": 0, "avg_confidence": 85},
                "avg_font_size_pt": 12.0,
                "preprocess_meta": prep_meta,
            }
        except Exception:
            return {
                "text": "",
                "html": "<p>Could not extract text from document.</p>",
                "words": [],
                "fuzzy_words": [],
                "line_boxes": [],
                "stats": {"word_count": 0, "fuzzy_count": 0, "avg_confidence": 0},
                "avg_font_size_pt": 12.0,
                "preprocess_meta": prep_meta,
            }

    # Process word-by-word data
    n_boxes = len(data["text"])
    lines: List[List[Dict[str, Any]]] = []
    current_line: List[Dict[str, Any]] = []
    last_line_num = -1
    last_block_num = -1

    word_heights: List[float] = []
    confidences: List[float] = []
    all_words: List[Dict[str, Any]] = []
    fuzzy_words: List[Dict[str, Any]] = []
    total_words = 0

    threshold = float(getattr(conf, "OCR_LOW_CONFIDENCE", 70))

    for i in range(n_boxes):
        w_text = data["text"][i].strip()
        conf_score = float(data["conf"][i])

        if not w_text or conf_score < 0:
            continue

        total_words += 1
        confidences.append(conf_score)

        # Scale coordinates back to original image space
        orig_left = int(round(data["left"][i] / scale_factor))
        orig_top = int(round(data["top"][i] / scale_factor))
        orig_width = int(round(data["width"][i] / scale_factor))
        orig_height = int(round(data["height"][i] / scale_factor))

        if orig_height > 4:
            word_heights.append(orig_height)

        cur_line_num = data["line_num"][i]
        cur_block_num = data["block_num"][i]
        cur_par_num = data.get("par_num", [0] * n_boxes)[i]
        cur_word_num = data.get("word_num", [0] * n_boxes)[i]

        is_fuzzy, reasons = detect_suspicious_word(w_text, conf_score, lang=use_lang, threshold=threshold)

        # Heatmap tier: red < 60, amber 60-80, high >= 80
        if conf_score < 60 or is_fuzzy:
            conf_tier = "low"
        elif conf_score < 80:
            conf_tier = "med"
        else:
            conf_tier = "high"

        word_id = f"w_p{page_num}_{total_words}"

        word_info = {
            "id": word_id,
            "text": w_text,
            "conf": round(conf_score, 1),
            "conf_tier": conf_tier,
            "is_fuzzy": is_fuzzy,
            "fuzzy_reasons": reasons,
            "bbox": (orig_left, orig_top, orig_width, orig_height),
            "line_num": cur_line_num,
            "block_num": cur_block_num,
            "par_num": cur_par_num,
            "word_num": cur_word_num,
            "page": page_num,
            "reviewed": False,
            "accepted": False,
            "edited_text": None,
        }

        all_words.append(word_info)
        if is_fuzzy:
            fuzzy_words.append(word_info)

        # Group into lines
        if cur_line_num != last_line_num or cur_block_num != last_block_num:
            if current_line:
                lines.append(current_line)
                current_line = []
            last_line_num = cur_line_num
            last_block_num = cur_block_num

        current_line.append(word_info)

    if current_line:
        lines.append(current_line)

    # Estimate average font size in points: pt = px * 72 / DPI
    if word_heights:
        sorted_heights = sorted(word_heights)
        med_height = sorted_heights[len(sorted_heights) // 2]
        est_pt = round((med_height * 72.0 / dpi) * 1.25, 1)
        est_pt = max(8.0, min(est_pt, 36.0))
    else:
        est_pt = 12.0

    # Build HTML representation with word spans and heatmap attributes
    html_paragraphs: List[str] = []
    current_para: List[str] = []

    for line in lines:
        line_tokens = []
        for w in line:
            escaped_text = html.escape(w["text"])
            classes = ["ocr-word"]
            if w["is_fuzzy"]:
                classes.append("docedit-fuzzy")

            fuzzy_attr = ' data-fuzzy-word="true"' if w["is_fuzzy"] else ""
            title_attr = f' title="Word: {escaped_text} | Conf: {w["conf"]}%' + (f' | Flagged: {", ".join(w["fuzzy_reasons"])}' if w["fuzzy_reasons"] else "") + '"'

            line_tokens.append(
                f'<span class="{" ".join(classes)}" data-word-id="{w["id"]}" '
                f'data-conf="{w["conf"]}" data-conf-tier="{w["conf_tier"]}"'
                f'{fuzzy_attr}{title_attr}>{escaped_text}</span>'
            )
        current_para.append(" ".join(line_tokens))

        last_word = line[-1]["text"] if line else ""
        if last_word.endswith((".", "!", "?", "।", "؟")) or len(current_para) >= 4:
            html_paragraphs.append(f"<p>{'<br>'.join(current_para)}</p>")
            current_para = []

    if current_para:
        html_paragraphs.append(f"<p>{'<br>'.join(current_para)}</p>")

    html_result = "\n".join(html_paragraphs) if html_paragraphs else "<p></p>"
    plain_text = " ".join(w["text"] for w in all_words)

    line_boxes: List[Dict[str, Any]] = []
    for line in lines:
        if not line:
            continue
        min_l = min(w["bbox"][0] for w in line)
        min_t = min(w["bbox"][1] for w in line)
        max_r = max(w["bbox"][0] + w["bbox"][2] for w in line)
        max_b = max(w["bbox"][1] + w["bbox"][3] for w in line)
        line_boxes.append({
            "text": " ".join(w["text"] for w in line),
            "bbox": (min_l, min_t, max_r - min_l, max_b - min_t),
            "words": line,
            "has_fuzzy": any(w["is_fuzzy"] for w in line),
        })

    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    return {
        "text": plain_text,
        "html": html_result,
        "words": all_words,
        "fuzzy_words": fuzzy_words,
        "line_boxes": line_boxes,
        "stats": {
            "word_count": total_words,
            "fuzzy_count": len(fuzzy_words),
            "avg_confidence": avg_conf,
        },
        "avg_font_size_pt": est_pt,
        "preprocess_meta": prep_meta,
        "scale_factor": scale_factor,
    }
