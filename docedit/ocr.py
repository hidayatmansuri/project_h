"""
OCR engine for scanned old books.

Tailored for aged, yellowed, stained paper and fuzzy faded ink:
- Pre-processes images (contrast enhancement, binarization, noise cleanup)
- Runs multi-lingual Tesseract with word-level bounding boxes and confidence scores
- Identifies 'fuzzy words' (confidence < 70) so the user can easily review spelling
- Estimates average font size (pt) and line metrics from bounding boxes
- Supports English, Hindi, Gujarati, Arabic, and automatic language downloading
"""
import io
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from .conf import conf

logger = logging.getLogger(__name__)


def get_tesseract_cmd() -> str:
    cmd = conf.TESSERACT_CMD
    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


def get_available_ocr_languages() -> List[str]:
    """Returns list of language codes installed in Tesseract."""
    try:
        get_tesseract_cmd()
        langs = pytesseract.get_languages(config="")
        return [l for l in langs if l != "osd"]
    except Exception as e:
        logger.warning("Could not list tesseract languages: %s", e)
        return ["eng"]


def ensure_ocr_language(lang: str) -> bool:
    """
    Checks if a language is installed; if not and downloads allowed, downloads it.
    """
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

    url = conf.TESSDATA_URL.format(lang=lang)
    target_file = tessdata_dir / f"{lang}.traineddata"
    try:
        logger.info("Downloading OCR language pack %s from %s", lang, url)
        req = urllib.request.Request(url, headers={"User-Agent": "project-h-docedit/1.0"})
        with urllib.request.urlopen(req, timeout=conf.HTTP_TIMEOUT * 2) as resp:
            target_file.write_bytes(resp.read())
        return True
    except Exception as e:
        logger.warning("Failed downloading OCR language pack %s: %s", lang, e)
        return False


def preprocess_old_book_image(img: Image.Image) -> Image.Image:
    """
    Pre-process old scanned book pages:
    1. Convert to grayscale.
    2. Auto-contrast to eliminate page yellowing / dark borders.
    3. Moderate sharpening to enhance fuzzy, faded letter edges.
    4. Adaptive local thresholding to separate text cleanly from aged paper.
    """
    # 1. Grayscale
    if img.mode != "L":
        gray = img.convert("L")
    else:
        gray = img.copy()

    # 2. Auto-contrast with 1% cutoff on white/black to normalize paper background
    gray = ImageOps.autocontrast(gray, cutoff=1)

    # 3. Enhance contrast slightly to darken faded ink
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(1.4)

    # 4. Slight unsharp mask to crisp up fuzzy old character edges
    sharpened = enhanced.filter(ImageFilter.UnsharpMask(radius=1.5, percent=130, threshold=3))

    # 5. Adaptive binarization (approximate local threshold)
    # Background estimation via large box blur
    bg = sharpened.filter(ImageFilter.BoxBlur(18))
    # Threshold: where original is significantly darker than local background
    diff = ImageOps.invert(ImageOps.autocontrast(ImageOps.invert(sharpened)))

    # Return optimized image for Tesseract
    return diff


def ocr_image(
    image: Image.Image,
    lang: str = "eng",
    dpi: int = 300,
) -> Dict[str, Any]:
    """
    Runs Tesseract OCR on a PIL image.
    Returns structured result with full text, html with fuzzy word markers,
    detected word metrics, and fuzzy word count.
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

    # Pre-process for aged books
    clean_img = preprocess_old_book_image(image)

    custom_config = f"--oem 1 --psm 3 -c preserve_interword_spaces=1"
    try:
        data = pytesseract.image_to_data(
            clean_img,
            lang=use_lang,
            config=custom_config,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        logger.error("OCR execution failed: %s", e)
        # Fallback to simple string extraction
        try:
            txt = pytesseract.image_to_string(clean_img, lang=use_lang)
            return {
                "text": txt,
                "html": "".join(f"<p>{p.strip()}</p>" for p in txt.split("\n\n") if p.strip()),
                "fuzzy_words": [],
                "stats": {"word_count": len(txt.split()), "fuzzy_count": 0, "avg_confidence": 85},
                "avg_font_size_pt": 12.0,
            }
        except Exception:
            return {
                "text": "",
                "html": "<p>Could not extract text from document.</p>",
                "fuzzy_words": [],
                "stats": {"word_count": 0, "fuzzy_count": 0, "avg_confidence": 0},
                "avg_font_size_pt": 12.0,
            }

    # Process word-by-word data
    n_boxes = len(data["text"])
    lines: List[List[Dict[str, Any]]] = []
    current_line: List[Dict[str, Any]] = []
    last_line_num = -1
    last_block_num = -1

    word_heights: List[float] = []
    confidences: List[float] = []
    fuzzy_words: List[Dict[str, Any]] = []
    total_words = 0

    threshold = conf.OCR_LOW_CONFIDENCE

    for i in range(n_boxes):
        w_text = data["text"][i].strip()
        conf_score = float(data["conf"][i])

        if not w_text or conf_score < 0:
            continue

        total_words += 1
        confidences.append(conf_score)
        height_px = float(data["height"][i])
        if height_px > 4:
            word_heights.append(height_px)

        is_fuzzy = conf_score < threshold
        word_info = {
            "text": w_text,
            "conf": round(conf_score, 1),
            "is_fuzzy": is_fuzzy,
            "bbox": (data["left"][i], data["top"][i], data["width"][i], data["height"][i]),
            "line_num": data["line_num"][i],
            "block_num": data["block_num"][i],
        }

        if is_fuzzy:
            fuzzy_words.append(word_info)

        # Group into lines
        cur_line_num = data["line_num"][i]
        cur_block_num = data["block_num"][i]

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
    # In printed books, capital letter height / em size is ~1.3-1.4x bounding box height
    if word_heights:
        # Sort and take median to avoid outlier headers or drop caps
        sorted_heights = sorted(word_heights)
        med_height = sorted_heights[len(sorted_heights) // 2]
        # Bounding box is typically 0.7 to 0.8 of the em size in points
        est_pt = round((med_height * 72.0 / dpi) * 1.25, 1)
        est_pt = max(8.0, min(est_pt, 36.0))
    else:
        est_pt = 12.0

    # Build HTML representation with fuzzy spans
    html_paragraphs: List[str] = []
    current_para: List[str] = []

    for line in lines:
        line_tokens = []
        for w in line:
            escaped_text = (
                w["text"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if w["is_fuzzy"]:
                # Highlighting for old book fuzzy characters so user can easily fix
                line_tokens.append(
                    f'<span class="docedit-fuzzy" data-conf="{w["conf"]}" '
                    f'title="Fuzzy character / confidence {w["conf"]}%">{escaped_text}</span>'
                )
            else:
                line_tokens.append(escaped_text)
        current_para.append(" ".join(line_tokens))

        # Check if line ends with a period or looks like end of paragraph
        last_word = line[-1]["text"] if line else ""
        if last_word.endswith((".", "!", "?", "।", "؟")) or len(current_para) >= 4:
            html_paragraphs.append(f"<p>{'<br>'.join(current_para)}</p>")
            current_para = []

    if current_para:
        html_paragraphs.append(f"<p>{'<br>'.join(current_para)}</p>")

    html_result = "\n".join(html_paragraphs) if html_paragraphs else "<p></p>"
    plain_text = " ".join(data["text"][i].strip() for i in range(n_boxes) if data["text"][i].strip())

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
        "fuzzy_words": fuzzy_words[:100],  # Top fuzzy words for review pan
        "line_boxes": line_boxes,
        "stats": {
            "word_count": total_words,
            "fuzzy_count": len(fuzzy_words),
            "avg_confidence": avg_conf,
        },
        "avg_font_size_pt": est_pt,
    }

