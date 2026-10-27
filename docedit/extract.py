"""
Document extraction pipeline preserving layout, tables, lines, and formatting.

Inspects uploaded files:
- Word DOCX: extracts full paragraph styles, headings, alignments, and TABLES in exact order.
- PDF: extracts text, tables via find_tables(), and horizontal vector lines via get_drawings().
- Scanned Images: runs aged-book OCR with line detection and structure preservation.
- Text/Markdown/HTML: converts markdown tables and horizontal rules into styled elements.
"""
import html
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
import numpy as np

from .conf import EXTENSION_KINDS, conf
from .embedded_fonts import extract_all_embedded_fonts, serialize_embedded_font_summary
from .fontmatch import (
    clean_pdf_font_name,
    detect_visual_font_for_scanned_book,
    generate_document_all_fonts_css,
    is_non_latin_script,
    resolve_font_with_fallback,
)
from .ocr import ocr_image
from .security import sanitize_document_html, sanitize_font_name

# Guard against decompression bomb DoS
Image.MAX_IMAGE_PIXELS = getattr(conf, "MAX_IMAGE_PIXELS", 50_000_000)

logger = logging.getLogger(__name__)


def extract_document(
    file_path: Path,
    ocr_lang: str = "eng",
    work_dir: Optional[Path] = None,
    sid: Optional[str] = None,
    progress_callback=None,
    ocr_profile: Optional[str] = None,
    ocr_deskew: Optional[bool] = None,
    ocr_dewarp: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Main extraction dispatcher preserving tables, lines, and layout.
    For non-editable documents (PDF and images with text), preserves separate pages,
    exact layout geometry, background drawings/tables, and extracts in-place text blocks.
    Sanitizes all extracted HTML with an allowlist before returning.
    """
    ext = file_path.suffix.lstrip(".").lower()
    kind = EXTENSION_KINDS.get(ext, "unknown")

    if progress_callback:
        progress_callback(10, f"Analyzing {ext.upper()} document structure...")

    if kind == "image":
        res = _extract_from_image(
            file_path,
            ocr_lang=ocr_lang,
            work_dir=work_dir,
            sid=sid,
            progress_callback=progress_callback,
            ocr_profile=ocr_profile,
            ocr_deskew=ocr_deskew,
            ocr_dewarp=ocr_dewarp,
        )
    elif kind == "pdf":
        res = _extract_from_pdf(
            file_path,
            ocr_lang=ocr_lang,
            work_dir=work_dir,
            sid=sid,
            progress_callback=progress_callback,
            ocr_profile=ocr_profile,
            ocr_deskew=ocr_deskew,
            ocr_dewarp=ocr_dewarp,
        )
    elif kind == "docx":
        res = _extract_from_docx(file_path, progress_callback=progress_callback)
    elif kind in ("text", "markdown", "html"):
        res = _extract_from_text(file_path, kind=kind, progress_callback=progress_callback)
    else:
        res = _extract_from_text(file_path, kind="text", progress_callback=progress_callback)

    if res and res.get("html"):
        res["html"] = sanitize_document_html(res["html"])

    return res


def _detect_image_horizontal_lines(img_gray: Image.Image) -> List[int]:
    """
    Detects y-coordinates of horizontal divider lines in a scanned page image
    using horizontal projection.
    """
    try:
        arr = np.array(img_gray)
        height, width = arr.shape
        if width < 100 or height < 100:
            return []

        dark_mask = arr < 130
        horiz_sum = np.sum(dark_mask, axis=1)

        min_line_len = width * 0.25
        line_indices = np.where(horiz_sum >= min_line_len)[0]

        if len(line_indices) == 0:
            return []

        detected_y = []
        group = [line_indices[0]]
        for idx in line_indices[1:]:
            if idx == group[-1] + 1:
                group.append(idx)
            else:
                if 1 <= len(group) <= 8:
                    detected_y.append(int(np.mean(group)))
                group = [idx]
        if 1 <= len(group) <= 8:
            detected_y.append(int(np.mean(group)))

        return detected_y
    except Exception as e:
        logger.debug("Line detection error: %s", e)
        return []


def _extract_from_image(
    file_path: Path,
    ocr_lang: str = "eng",
    work_dir: Optional[Path] = None,
    sid: Optional[str] = None,
    progress_callback=None,
    ocr_profile: Optional[str] = None,
    ocr_deskew: Optional[bool] = None,
    ocr_dewarp: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Extracts text, divider lines, and separate page structures from scanned book pages via OCR.
    Preserves original image background, tables, borders, and separate pages.
    """
    if progress_callback:
        progress_callback(20, "Loading image and analyzing page layout & lines...")

    Image.MAX_IMAGE_PIXELS = getattr(conf, "MAX_IMAGE_PIXELS", 50_000_000)
    try:
        img = Image.open(str(file_path))
    except Image.DecompressionBombError as e:
        raise ValueError(
            f"Image decompression bomb detected: image exceeds maximum pixel limit of {conf.MAX_IMAGE_PIXELS:,} pixels."
        ) from e

    pages_html = []
    pages_data = []
    all_fuzzy_words = []
    all_words = []
    all_text = []
    page_count = 0
    font_sizes = []

    try:
        frame_idx = 0
        while True:
            if page_count >= conf.MAX_PAGES:
                raise ValueError(f"Image document exceeds maximum page limit of {conf.MAX_PAGES} pages.")
            img.seek(frame_idx)
            orig_w, orig_h = img.size
            if orig_w * orig_h > conf.MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Image frame {frame_idx + 1} ({orig_w}x{orig_h} = {orig_w * orig_h:,} pixels) "
                    f"exceeds maximum allowed limit of {conf.MAX_IMAGE_PIXELS:,} pixels."
                )
            page_count += 1
            if progress_callback:
                progress_callback(30 + min(40, frame_idx * 10), f"Extracting page {page_count}...")

            cur_frame = img.copy()

            # Read real DPI from metadata (fallback: derive from page width assuming ~8.27 in A4 width)
            info_dpi = cur_frame.info.get("dpi")
            real_dpi = None
            if isinstance(info_dpi, (tuple, list)) and len(info_dpi) >= 2:
                try:
                    real_dpi = float(info_dpi[0])
                except (ValueError, TypeError):
                    pass
            elif isinstance(info_dpi, (int, float)) and info_dpi > 0:
                real_dpi = float(info_dpi)

            if not real_dpi or real_dpi < 30 or real_dpi > 2400:
                derived = orig_w / 8.27
                if 72 <= derived <= 600:
                    real_dpi = round(derived, 1)
                else:
                    real_dpi = float(conf.OCR_DPI)

            if work_dir:
                try:
                    p_path = work_dir / f"page_{page_count}.png"
                    if cur_frame.mode not in ("RGB", "RGBA"):
                        cur_rgb = cur_frame.convert("RGB")
                        cur_rgb.save(str(p_path), format="PNG")
                    else:
                        cur_frame.save(str(p_path), format="PNG")
                except Exception as e:
                    logger.debug("Could not cache page image: %s", e)

            gray = cur_frame.convert("L")
            detected_lines = _detect_image_horizontal_lines(gray)

            res = ocr_image(
                cur_frame,
                lang=ocr_lang,
                dpi=int(round(real_dpi)),
                profile=ocr_profile,
                deskew=ocr_deskew,
                dewarp=ocr_dewarp,
                page_num=page_count,
            )
            line_boxes = res.get("line_boxes", [])
            for w_item in res.get("words", []):
                all_words.append(w_item)
            avg_pt = res.get("avg_font_size_pt", 12.0)
            if avg_pt:
                font_sizes.append(avg_pt)

            page_blocks = []
            block_html_items = []
            b_idx = 0

            for lb in line_boxes:
                b_text = lb["text"].strip()
                if not b_text:
                    continue
                lx, ly, lw, lh = lb["bbox"]
                left_pct = round((lx / max(1, orig_w)) * 100, 4)
                top_pct = round((ly / max(1, orig_h)) * 100, 4)
                width_pct = round((lw / max(1, orig_w)) * 100, 4)
                height_pct = round((lh / max(1, orig_h)) * 100, 4)
                est_line_pt = round(lh * 72.0 / real_dpi, 1)
                est_line_pt = max(6.0, min(est_line_pt, 72.0))

                is_non_latin, script_name = is_non_latin_script(b_text)
                readonly_reason = (
                    f"Non-Latin script ({script_name.title() if script_name else 'Complex'}) is currently read-only. "
                    f"PyMuPDF insert_text does not shape Arabic/Indic scripts and does not handle RTL."
                ) if is_non_latin else None

                b_id = f"p{page_count}_b{b_idx}"
                page_blocks.append({
                    "id": b_id,
                    "text": b_text,
                    "unit": "px",
                    "bbox": [lx, ly, lx + lw, ly + lh],
                    "orig_bbox": [lx, ly, lx + lw, ly + lh],
                    "size_src": lh,
                    "font_size_pt": est_line_pt,
                    "line_height_src": lh,
                    "left_pct": left_pct,
                    "top_pct": top_pct,
                    "width_pct": width_pct,
                    "height_pct": height_pct,
                    "rotation": 0,
                    "font_name": "EB Garamond",
                    "orig_font_name": "EB Garamond",
                    "orig_font_size_pt": est_line_pt,
                    "orig_text": b_text,
                    "orig_is_bold": False,
                    "orig_is_italic": False,
                    "orig_is_underline": False,
                    "is_modified": False,
                    "is_header": est_line_pt >= 16,
                    "has_fuzzy": lb.get("has_fuzzy", False) and not is_non_latin,
                    "is_readonly": is_non_latin,
                    "readonly_reason": readonly_reason,
                    "script": script_name or "latin",
                    "page": page_count,
                    "words": lb.get("words", []),
                })

                word_spans = []
                for w in lb.get("words", []):
                    w_esc = html.escape(w["text"])
                    is_w_fuzzy = w.get("is_fuzzy") and not is_non_latin
                    w_cls = "ocr-word" + (" docedit-fuzzy" if is_w_fuzzy else "")
                    fuzzy_attr = ' data-fuzzy-word="true"' if is_w_fuzzy else ""
                    conf_val = w.get("conf", 85)
                    tier = w.get("conf_tier", "high")
                    word_spans.append(
                        f'<span class="{w_cls}" data-word-id="{w.get("id", "")}" '
                        f'data-conf="{conf_val}" data-conf-tier="{tier}"{fuzzy_attr}>{w_esc}</span>'
                    )
                escaped = " ".join(word_spans) if word_spans else html.escape(b_text)

                readonly_class = " docedit-block-readonly" if is_non_latin else ""
                readonly_attr = (
                    f'contenteditable="false" data-readonly="true" '
                    f'data-readonly-reason="{html.escape(readonly_reason or "")}" '
                    f'data-script="{html.escape(script_name or "")}"'
                ) if is_non_latin else 'contenteditable="true"'
                readonly_badge = (
                    f'<span class="docedit-readonly-badge" title="{html.escape(readonly_reason or "")}">'
                    f'<i class="fa-solid fa-lock"></i> {html.escape((script_name or "Non-Latin").title())} (Read-Only)</span>'
                ) if is_non_latin else ""

                block_html_items.append(
                    f'<div class="docedit-text-block{" has-fuzzy" if (lb.get("has_fuzzy") and not is_non_latin) else ""}{readonly_class}" '
                    f'{readonly_attr} spellcheck="false" '
                    f'data-block-id="{b_id}" data-page="{page_count}" data-font-size-pt="{est_line_pt}" '
                    f'style="--x-src: {lx}; --y-src: {ly}; --w-src: {lw}; --h-src: {lh}; --size-src: {lh};">'
                    f'{readonly_badge}{escaped}</div>'
                )
                b_idx += 1

            img_url = f"/docedit/api/page-image/{sid}/{page_count}/" if sid else f"page_{page_count}.png"

            pages_data.append({
                "page_num": page_count,
                "unit": "px",
                "width": orig_w,
                "height": orig_h,
                "dpi": round(real_dpi, 1),
                "aspect_ratio": round(orig_h / max(1, orig_w), 4),
                "image_url": img_url,
                "blocks": page_blocks,
            })

            sheet_html = f'''<div class="docedit-page-sheet" data-page="{page_count}" id="doceditPage_{page_count}">
  <div class="page-sheet-header">
    <div class="page-sheet-badge"><i class="fa-solid fa-file-image"></i> Page {page_count}</div>
    <div class="page-sheet-dims">{orig_w} × {orig_h} px ({int(round(real_dpi))} DPI)</div>
  </div>
  <div class="page-sheet-canvas" style="aspect-ratio: {orig_w} / {orig_h}; --scale: 1.0; --page-width: {orig_w};">
    <img class="page-bg-img" src="{img_url}" alt="Page {page_count} Original Layout" draggable="false" />
    <div class="page-text-overlay">
      {"".join(block_html_items)}
    </div>
  </div>
</div>'''
            pages_html.append(sheet_html)
            all_text.append(res["text"])
            for fw in res.get("fuzzy_words", []):
                if not is_non_latin_script(fw.get("text", ""))[0]:
                    fw["page"] = page_count
                    all_fuzzy_words.append(fw)

            frame_idx += 1
    except EOFError:
        pass

    full_text = "\n\n".join(all_text)
    combined_html = "\n".join(pages_html)
    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else 12.0
    matched_font = detect_visual_font_for_scanned_book(full_text)
    font_res = resolve_font_with_fallback(matched_font, text_sample=full_text, sid=sid)
    all_resolved_fonts = [font_res]

    for p in pages_data:
        for b in p["blocks"]:
            b["font_info"] = dict(font_res)
            b["font_name"] = font_res["used"]
            b["orig_font_name"] = font_res["used"]
            b["font_requested"] = font_res["requested"]

    all_fonts_css = generate_document_all_fonts_css(all_resolved_fonts, sid=sid)

    if sid and all_words:
        try:
            from .storage import save_session_words
            save_session_words(sid, all_words)
        except Exception as e:
            logger.debug("Could not save session words: %s", e)

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": font_res["used"],
        "font_size_pt": avg_size,
        "is_layout_preserved": True,
        "pages": pages_data,
        "all_fonts_css": all_fonts_css,
        "stats": {
            "page_count": page_count,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
            "fuzzy_word_count": len(all_fuzzy_words),
        },
        "fuzzy_words": all_fuzzy_words[:100],
        "words": all_words,
        "needs_ocr": True,
        "is_scanned": True,
    }


def _extract_from_pdf(
    file_path: Path,
    ocr_lang: str = "eng",
    work_dir: Optional[Path] = None,
    sid: Optional[str] = None,
    progress_callback=None,
    ocr_profile: Optional[str] = None,
    ocr_deskew: Optional[bool] = None,
    ocr_dewarp: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Extracts text, TABLES, lines, and formatting from PDF.
    Preserves exact tables, vector rules, and separate page structures.
    Renders high-resolution background pages so all tables, lines, borders,
    and graphics remain completely intact while text is editable in-place.
    Identifies embedded fonts, preserves span-level typography and colors,
    and groups lines into paragraph blocks with union bounding boxes.
    """
    import pymupdf

    if progress_callback:
        progress_callback(20, "Inspecting PDF tables, lines, and typography...")

    doc = pymupdf.open(str(file_path))
    page_count = len(doc)
    if page_count > conf.MAX_PAGES:
        doc.close()
        raise ValueError(f"Document exceeds maximum page limit of {conf.MAX_PAGES} pages (found {page_count} pages).")

    # Extract all embedded fonts from the document
    embedded_catalog = extract_all_embedded_fonts(doc, session_dir=work_dir)
    embedded_summary = {
        clean_name: serialize_embedded_font_summary(f_info)
        for clean_name, f_info in embedded_catalog.get("by_clean_name", {}).items()
    }

    pages_html = []
    pages_data = []
    all_text = []
    all_fuzzy_words = []
    all_words = []
    detected_fonts: Dict[str, int] = {}
    font_sizes: List[float] = []
    pages_needing_ocr = 0
    all_resolved_fonts: List[Dict[str, Any]] = []

    for idx, page in enumerate(doc):
        page_num = idx + 1
        page_text = page.get_text()
        rect = page.rect
        cropbox = getattr(page, "cropbox", rect)
        p_width = round(rect.width, 1)
        p_height = round(rect.height, 1)
        crop_x0 = round(cropbox.x0, 2)
        crop_y0 = round(cropbox.y0, 2)

        if work_dir:
            try:
                pix = page.get_pixmap(dpi=150)
                pix.save(str(work_dir / f"page_{page_num}.png"))
            except Exception as e:
                logger.debug("Failed saving PDF page image: %s", e)

        img_url = f"/docedit/api/page-image/{sid}/{page_num}/" if sid else f"page_{page_num}.png"

        page_blocks = []
        block_html_items = []
        b_idx = 0

        # Build font resource mapping (e.g. F1 -> TimesNewRomanPSMT)
        font_res_map: Dict[str, str] = {}
        try:
            for f_info in page.get_fonts(full=True):
                basefont = f_info[3] if len(f_info) > 3 else ""
                res_name = f_info[4] if len(f_info) > 4 else ""
                if res_name and basefont:
                    font_res_map[res_name] = basefont
                    font_res_map[res_name.lstrip("/")] = basefont
        except Exception:
            pass

        dict_blocks = page.get_text("dict").get("blocks", [])
        has_text_layer = len(page_text.strip()) > 15

        if has_text_layer:
            for b in dict_blocks:
                if b.get("type") == 0:  # Text block
                    raw_lines = b.get("lines", [])
                    if not raw_lines:
                        continue

                    current_paragraph: List[Dict[str, Any]] = []

                    def emit_paragraph(p_lines: List[Dict[str, Any]]) -> None:
                        nonlocal b_idx
                        if not p_lines:
                            return

                        all_spans = [s for l in p_lines for s in l["spans"]]
                        if not all_spans:
                            return

                        min_x0 = min(l["bbox"][0] for l in p_lines)
                        min_y0 = min(l["bbox"][1] for l in p_lines)
                        max_x1 = max(l["bbox"][2] for l in p_lines)
                        max_y1 = max(l["bbox"][3] for l in p_lines)

                        w_box = max(1.0, max_x1 - min_x0)
                        h_box = max(1.0, max_y1 - min_y0)
                        avg_lh = sum(max(1.0, l["bbox"][3] - l["bbox"][1]) for l in p_lines) / max(1, len(p_lines))

                        first_span = all_spans[0]
                        origin = first_span.get("origin", [min_x0, max_y1])

                        # Dominant font & size
                        font_counts: Dict[str, int] = {}
                        for s in all_spans:
                            f = s.get("font") or "EB Garamond"
                            font_counts[f] = font_counts.get(f, 0) + max(1, len(s.get("text", "")))
                        dom_font = max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else "EB Garamond"
                        dom_size = max(all_spans, key=lambda s: len(s.get("text", ""))).get("size", 12.0)

                        is_bold = any(s.get("is_bold") for s in all_spans)
                        is_italic = any(s.get("is_italic") for s in all_spans)

                        # Dominant colour
                        color_counts: Dict[Tuple[str, int, Tuple[float, float, float]], int] = {}
                        for s in all_spans:
                            key = (s.get("colour", "#000000"), s.get("color_int", 0), s.get("color_rgb", (0.0, 0.0, 0.0)))
                            color_counts[key] = color_counts.get(key, 0) + max(1, len(s.get("text", "")))
                        dom_color_entry = max(color_counts.items(), key=lambda x: x[1])[0] if color_counts else ("#000000", 0, (0.0, 0.0, 0.0))
                        dom_hex, dom_int, dom_rgb = dom_color_entry

                        rot = p_lines[0].get("rotation", 0)
                        dir_vec = p_lines[0].get("dir", [1.0, 0.0])

                        # Render positions in canvas space
                        if rot == 90:
                            # Vertical upwards (bottom-to-top)
                            render_x = min_x0
                            render_y = max_y1
                            render_w = h_box
                            render_h = w_box
                            transform_css = "transform: rotate(-90deg); transform-origin: top left; "
                        elif rot == 270:
                            # Vertical downwards (top-to-bottom)
                            render_x = max_x1
                            render_y = min_y0
                            render_w = h_box
                            render_h = w_box
                            transform_css = "transform: rotate(90deg); transform-origin: top left; "
                        elif rot == 180:
                            # Upside-down
                            render_x = max_x1
                            render_y = max_y1
                            render_w = w_box
                            render_h = h_box
                            transform_css = "transform: rotate(180deg); transform-origin: top left; "
                        else:
                            render_x = min_x0
                            render_y = min_y0
                            render_w = w_box
                            render_h = h_box
                            transform_css = ""

                        full_text = "\n".join(l["text"] for l in p_lines)
                        b_id = f"p{page_num}_b{b_idx}"

                        is_non_latin, script_name = is_non_latin_script(full_text)
                        readonly_reason = (
                            f"Non-Latin script ({script_name.title() if script_name else 'Complex'}) is currently read-only. "
                            f"PyMuPDF insert_text does not shape Arabic/Indic scripts and does not handle RTL."
                        ) if is_non_latin else None

                        left_pct = round((min_x0 / max(1, p_width)) * 100, 3)
                        top_pct = round((min_y0 / max(1, p_height)) * 100, 3)
                        width_pct = round((w_box / max(1, p_width)) * 100, 3)
                        height_pct = round((h_box / max(1, p_height)) * 100, 3)

                        if dom_font:
                            detected_fonts[dom_font] = detected_fonts.get(dom_font, 0) + len(full_text)
                        if dom_size > 4:
                            font_sizes.append(dom_size)

                        b_font_res = resolve_font_with_fallback(
                            dom_font,
                            embedded_catalog=embedded_summary,
                            text_sample=full_text,
                            is_bold=is_bold,
                            is_italic=is_italic,
                            sid=sid,
                        )
                        all_resolved_fonts.append(b_font_res)
                        resolved_used_name = b_font_res["used"]
                        resolved_req_name = b_font_res["requested"]

                        page_blocks.append({
                            "id": b_id,
                            "text": full_text,
                            "unit": "pt",
                            "bbox": [round(min_x0, 1), round(min_y0, 1), round(max_x1, 1), round(max_y1, 1)],
                            "orig_bbox": [round(min_x0, 1), round(min_y0, 1), round(max_x1, 1), round(max_y1, 1)],
                            "render_x": round(render_x, 2),
                            "render_y": round(render_y, 2),
                            "render_w": round(render_w, 2),
                            "render_h": round(render_h, 2),
                            "size_src": dom_size,
                            "line_height_src": round(avg_lh, 2),
                            "left_pct": left_pct,
                            "top_pct": top_pct,
                            "width_pct": width_pct,
                            "height_pct": height_pct,
                            "rotation": rot,
                            "dir": dir_vec,
                            "origin": [round(origin[0], 2), round(origin[1], 2)],
                            "color": dom_hex,
                            "colour": dom_hex,
                            "color_int": dom_int,
                            "color_rgb": dom_rgb,
                            "font_info": b_font_res,
                            "font_name": resolved_used_name,
                            "font_size_pt": dom_size,
                            "orig_text": full_text,
                            "orig_font_name": resolved_used_name,
                            "font_requested": resolved_req_name,
                            "orig_font_size_pt": dom_size,
                            "orig_is_bold": is_bold,
                            "orig_is_italic": is_italic,
                            "orig_is_underline": False,
                            "is_modified": False,
                            "is_bold": is_bold,
                            "is_italic": is_italic,
                            "is_underline": False,
                            "is_header": dom_size >= 15,
                            "is_readonly": is_non_latin,
                            "readonly_reason": readonly_reason,
                            "script": script_name or "latin",
                            "page": page_num,
                            "lines": p_lines,
                            "spans": all_spans,
                        })

                        escaped_lines = [html.escape(l["text"]) for l in p_lines]
                        escaped_content = "<br>".join(escaped_lines)
                        is_serif = any(s in (resolved_used_name or "").lower() for s in ["times", "serif", "garamond", "georgia", "baskerville", "caslon", "cambria", "book", "minion", "palatino"])
                        fallback_generic = "serif" if is_serif else "sans-serif"
                        safe_font = html.escape(sanitize_font_name(resolved_used_name), quote=True) if resolved_used_name else ""
                        block_font_css = f"font-family: '{safe_font}', {fallback_generic}; " if safe_font else ""
                        weight_css = "font-weight: bold; " if is_bold else ""
                        style_css = "font-style: italic; " if is_italic else ""
                        color_css = f"color: {dom_hex}; --block-color: {dom_hex}; "

                        readonly_class = " docedit-block-readonly" if is_non_latin else ""
                        readonly_attr = (
                            f'contenteditable="false" data-readonly="true" '
                            f'data-readonly-reason="{html.escape(readonly_reason or "")}" '
                            f'data-script="{html.escape(script_name or "")}"'
                        ) if is_non_latin else 'contenteditable="true"'
                        readonly_badge = (
                            f'<span class="docedit-readonly-badge" title="{html.escape(readonly_reason or "")}">'
                            f'<i class="fa-solid fa-lock"></i> {html.escape((script_name or "Non-Latin").title())} (Read-Only)</span>'
                        ) if is_non_latin else ""

                        block_html_items.append(
                            f'<div class="docedit-text-block{readonly_class}" '
                            f'{readonly_attr} spellcheck="false" '
                            f'data-block-id="{b_id}" data-page="{page_num}" data-font-size-pt="{dom_size}" data-rotation="{rot}" '
                            f'style="--x-src: {round(render_x, 2)}; --y-src: {round(render_y, 2)}; --w-src: {round(render_w, 2)}; --h-src: {round(render_h, 2)}; --lh-src: {round(avg_lh, 2)}; --size-src: {dom_size}; {color_css}{transform_css}{block_font_css}{weight_css}{style_css}">'
                            f'{readonly_badge}{escaped_content}</div>'
                        )
                        b_idx += 1

                    for raw_line in raw_lines:
                        line_spans_raw = raw_line.get("spans", [])
                        if not line_spans_raw:
                            continue
                        line_str = "".join(s.get("text", "") for s in line_spans_raw).strip()
                        if not line_str:
                            continue

                        dx, dy = raw_line.get("dir", (1.0, 0.0))
                        if abs(dx) >= abs(dy):
                            line_rot = 0 if dx >= 0 else 180
                        else:
                            line_rot = 90 if dy < 0 else 270

                        line_bbox = list(raw_line.get("bbox", (0, 0, 0, 0)))

                        parsed_spans = []
                        for s in line_spans_raw:
                            s_text = s.get("text", "")
                            s_color_int = s.get("color", 0)
                            sr = (s_color_int >> 16) & 255
                            sg = (s_color_int >> 8) & 255
                            sb = s_color_int & 255
                            s_hex = f"#{sr:02x}{sg:02x}{sb:02x}"
                            s_rgb = (round(sr / 255.0, 3), round(sg / 255.0, 3), round(sb / 255.0, 3))
                            s_flags = s.get("flags", 0)
                            s_bold = bool(s_flags & (1 << 4))
                            s_italic = bool(s_flags & (1 << 1))
                            s_raw_f = s.get("font", "")
                            s_resolved_f = font_res_map.get(s_raw_f) or font_res_map.get(s_raw_f.lstrip("/")) or s_raw_f
                            s_fname = clean_pdf_font_name(s_resolved_f)
                            if s_fname:
                                s_fname = sanitize_font_name(s_fname, default="EB Garamond")
                            if not s_fname or s_fname.lower() in ("default", "unknown"):
                                s_fname = None
                            s_lower = (s_resolved_f or s_raw_f).lower()
                            if not s_bold and any(b_w in s_lower for b_w in ["bold", "black", "heavy", "semibold", "demibold", "bd"]):
                                s_bold = True
                            if not s_italic and any(it in s_lower for it in ["italic", "oblique", "slant", "kursiv"]):
                                s_italic = True
                            s_size = round(s.get("size", 12.0), 1)
                            s_origin = list(s.get("origin", (line_bbox[0], line_bbox[3])))

                            parsed_spans.append({
                                "text": s_text,
                                "font": s_fname or "EB Garamond",
                                "raw_font": s_raw_f,
                                "size": s_size,
                                "flags": s_flags,
                                "is_bold": s_bold,
                                "is_italic": s_italic,
                                "colour": s_hex,
                                "color": s_hex,
                                "color_int": s_color_int,
                                "color_rgb": s_rgb,
                                "origin": [round(s_origin[0], 2), round(s_origin[1], 2)],
                                "bbox": [round(x, 2) for x in s.get("bbox", line_bbox)],
                            })

                        parsed_line = {
                            "text": line_str,
                            "bbox": line_bbox,
                            "dir": [round(dx, 4), round(dy, 4)],
                            "rotation": line_rot,
                            "spans": parsed_spans,
                        }

                        if not current_paragraph:
                            current_paragraph.append(parsed_line)
                        else:
                            prev_line = current_paragraph[-1]
                            same_rot = (parsed_line["rotation"] == prev_line["rotation"])
                            if same_rot and line_rot == 0:
                                prev_y0 = prev_line["bbox"][1]
                                prev_y1 = prev_line["bbox"][3]
                                curr_y0 = parsed_line["bbox"][1]
                                prev_h = max(1.0, prev_y1 - prev_y0)
                                is_same_row = abs(curr_y0 - prev_y0) < 4.0
                                is_stacked = (curr_y0 >= prev_y0 - 2.0) and (curr_y0 - prev_y1 <= prev_h * 1.6)
                                if is_stacked and not is_same_row:
                                    current_paragraph.append(parsed_line)
                                else:
                                    emit_paragraph(current_paragraph)
                                    current_paragraph = [parsed_line]
                            else:
                                emit_paragraph(current_paragraph)
                                current_paragraph = [parsed_line]

                    if current_paragraph:
                        emit_paragraph(current_paragraph)

            all_text.append(page_text)
        else:
            pages_needing_ocr += 1
            pix = page.get_pixmap(dpi=conf.OCR_DPI)
            p_img = Image.open(io.BytesIO(pix.tobytes("png")))
            res = ocr_image(
                p_img,
                lang=ocr_lang,
                dpi=conf.OCR_DPI,
                profile=ocr_profile,
                deskew=ocr_deskew,
                dewarp=ocr_dewarp,
                page_num=page_num,
            )
            for w_item in res.get("words", []):
                all_words.append(w_item)
            avg_pt = res.get("avg_font_size_pt", 12.0)
            if avg_pt:
                font_sizes.append(avg_pt)

            for lb in res.get("line_boxes", []):
                b_text = lb["text"].strip()
                if not b_text:
                    continue
                lx, ly, lw, lh = lb["bbox"]
                left_pct = round((lx / max(1, pix.width)) * 100, 3)
                top_pct = round((ly / max(1, pix.height)) * 100, 3)
                width_pct = round((lw / max(1, pix.width)) * 100, 3)
                height_pct = round((lh / max(1, pix.height)) * 100, 3)
                est_line_pt = round(lh * 72.0 / conf.OCR_DPI, 1)

                pt_x = round(lx * (p_width / pix.width), 2)
                pt_y = round(ly * (p_height / pix.height), 2)
                pt_w = round(lw * (p_width / pix.width), 2)
                pt_h = round(lh * (p_height / pix.height), 2)
                bbox_calc = [pt_x, pt_y, round(pt_x + pt_w, 2), round(pt_y + pt_h, 2)]

                b_id = f"p{page_num}_b{b_idx}"
                ocr_font_res = resolve_font_with_fallback(
                    detect_visual_font_for_scanned_book(b_text),
                    text_sample=b_text,
                    sid=sid,
                )
                all_resolved_fonts.append(ocr_font_res)
                ocr_used_name = ocr_font_res["used"]
                ocr_req_name = ocr_font_res["requested"]

                is_non_latin, script_name = is_non_latin_script(b_text)
                readonly_reason = (
                    f"Non-Latin script ({script_name.title() if script_name else 'Complex'}) is currently read-only. "
                    f"PyMuPDF insert_text does not shape Arabic/Indic scripts and does not handle RTL."
                ) if is_non_latin else None

                page_blocks.append({
                    "id": b_id,
                    "text": b_text,
                    "unit": "pt",
                    "bbox": bbox_calc,
                    "orig_bbox": list(bbox_calc),
                    "render_x": pt_x,
                    "render_y": pt_y,
                    "render_w": pt_w,
                    "render_h": pt_h,
                    "size_src": est_line_pt,
                    "line_height_src": pt_h,
                    "left_pct": left_pct,
                    "top_pct": top_pct,
                    "width_pct": width_pct,
                    "height_pct": height_pct,
                    "rotation": 0,
                    "dir": [1.0, 0.0],
                    "origin": [pt_x, round(pt_y + pt_h * 0.82, 2)],
                    "color": "#000000",
                    "colour": "#000000",
                    "color_int": 0,
                    "color_rgb": (0.0, 0.0, 0.0),
                    "font_info": ocr_font_res,
                    "font_name": ocr_used_name,
                    "font_size_pt": est_line_pt,
                    "orig_text": b_text,
                    "orig_font_name": ocr_used_name,
                    "font_requested": ocr_req_name,
                    "orig_font_size_pt": est_line_pt,
                    "orig_is_bold": False,
                    "orig_is_italic": False,
                    "orig_is_underline": False,
                    "is_modified": False,
                    "is_bold": False,
                    "is_italic": False,
                    "is_underline": False,
                    "is_header": est_line_pt >= 15,
                    "has_fuzzy": lb.get("has_fuzzy", False) and not is_non_latin,
                    "is_readonly": is_non_latin,
                    "readonly_reason": readonly_reason,
                    "script": script_name or "latin",
                    "page": page_num,
                    "lines": [{
                        "text": b_text,
                        "bbox": bbox_calc,
                        "dir": [1.0, 0.0],
                        "rotation": 0,
                        "spans": [{
                            "text": b_text,
                            "font": "EB Garamond",
                            "raw_font": "EB Garamond",
                            "size": est_line_pt,
                            "flags": 0,
                            "is_bold": False,
                            "is_italic": False,
                            "colour": "#000000",
                            "color": "#000000",
                            "color_int": 0,
                            "color_rgb": (0.0, 0.0, 0.0),
                            "origin": [pt_x, round(pt_y + pt_h * 0.82, 2)],
                            "bbox": bbox_calc,
                        }],
                    }],
                    "spans": [{
                        "text": b_text,
                        "font": "EB Garamond",
                        "raw_font": "EB Garamond",
                        "size": est_line_pt,
                        "flags": 0,
                        "is_bold": False,
                        "is_italic": False,
                        "colour": "#000000",
                        "color": "#000000",
                        "color_int": 0,
                        "color_rgb": (0.0, 0.0, 0.0),
                        "origin": [pt_x, round(pt_y + pt_h * 0.82, 2)],
                        "bbox": bbox_calc,
                    }],
                    "words": lb.get("words", []),
                })
                word_spans = []
                for w in lb.get("words", []):
                    w_esc = html.escape(w["text"])
                    is_w_fuzzy = w.get("is_fuzzy") and not is_non_latin
                    w_cls = "ocr-word" + (" docedit-fuzzy" if is_w_fuzzy else "")
                    fuzzy_attr = ' data-fuzzy-word="true"' if is_w_fuzzy else ""
                    conf_val = w.get("conf", 85)
                    tier = w.get("conf_tier", "high")
                    word_spans.append(
                        f'<span class="{w_cls}" data-word-id="{w.get("id", "")}" '
                        f'data-conf="{conf_val}" data-conf-tier="{tier}"{fuzzy_attr}>{w_esc}</span>'
                    )
                escaped = " ".join(word_spans) if word_spans else html.escape(b_text)

                readonly_class = " docedit-block-readonly" if is_non_latin else ""
                readonly_attr = (
                    f'contenteditable="false" data-readonly="true" '
                    f'data-readonly-reason="{html.escape(readonly_reason or "")}" '
                    f'data-script="{html.escape(script_name or "")}"'
                ) if is_non_latin else 'contenteditable="true"'
                readonly_badge = (
                    f'<span class="docedit-readonly-badge" title="{html.escape(readonly_reason or "")}">'
                    f'<i class="fa-solid fa-lock"></i> {html.escape((script_name or "Non-Latin").title())} (Read-Only)</span>'
                ) if is_non_latin else ""

                block_html_items.append(
                    f'<div class="docedit-text-block{" has-fuzzy" if (lb.get("has_fuzzy") and not is_non_latin) else ""}{readonly_class}" '
                    f'{readonly_attr} spellcheck="false" '
                    f'data-block-id="{b_id}" data-page="{page_num}" data-font-size-pt="{est_line_pt}" '
                    f'style="--x-src: {pt_x}; --y-src: {pt_y}; --w-src: {pt_w}; --h-src: {pt_h}; --lh-src: {pt_h}; --size-src: {est_line_pt}; color: #000000; --block-color: #000000;">'
                    f'{readonly_badge}{escaped}</div>'
                )
                b_idx += 1

            all_text.append(res["text"])
            for fw in res.get("fuzzy_words", []):
                if not is_non_latin_script(fw.get("text", ""))[0]:
                    fw["page"] = page_num
                    all_fuzzy_words.append(fw)

        pages_data.append({
            "page_num": page_num,
            "unit": "pt",
            "width": p_width,
            "height": p_height,
            "crop_offset": [crop_x0, crop_y0],
            "aspect_ratio": round(p_height / max(1, p_width), 4),
            "image_url": img_url,
            "blocks": page_blocks,
        })

        sheet_html = f'''<div class="docedit-page-sheet" data-page="{page_num}" id="doceditPage_{page_num}">
  <div class="page-sheet-header">
    <div class="page-sheet-badge"><i class="fa-solid fa-file-pdf"></i> Page {page_num} of {page_count}</div>
    <div class="page-sheet-dims">{int(p_width)} × {int(p_height)} pt</div>
  </div>
  <div class="page-sheet-canvas" style="aspect-ratio: {p_width} / {p_height}; --scale: 1.0; --page-width: {p_width};">
    <img class="page-bg-img" src="{img_url}" alt="Page {page_num} Original Layout" draggable="false" />
    <div class="page-text-overlay">
      {"".join(block_html_items)}
    </div>
  </div>
</div>'''
        pages_html.append(sheet_html)

    full_text = "\n\n".join(all_text)
    combined_html = "\n".join(pages_html)

    if detected_fonts:
        dominant_font = max(detected_fonts.items(), key=lambda x: x[1])[0]
    else:
        dominant_font = detect_visual_font_for_scanned_book(full_text)

    dom_res = resolve_font_with_fallback(
        dominant_font,
        embedded_catalog=embedded_summary,
        text_sample=full_text,
        sid=sid,
    )
    all_resolved_fonts.append(dom_res)

    for p in pages_data:
        for b in p["blocks"]:
            if not b.get("font_info"):
                b["font_info"] = dict(dom_res)
                b["font_name"] = dom_res["used"]
                b["orig_font_name"] = dom_res["used"]
                b["font_requested"] = dom_res["requested"]

    all_fonts_css = generate_document_all_fonts_css(all_resolved_fonts, sid=sid)
    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else 12.0

    if sid and all_words:
        try:
            from .storage import save_session_words
            save_session_words(sid, all_words)
        except Exception as e:
            logger.debug("Could not save session words: %s", e)

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": dom_res["used"],
        "font_size_pt": avg_size,
        "is_layout_preserved": True,
        "pages": pages_data,
        "embedded_fonts": embedded_summary,
        "all_fonts_css": all_fonts_css,
        "stats": {
            "page_count": page_count,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
            "fuzzy_word_count": len(all_fuzzy_words),
        },
        "fuzzy_words": all_fuzzy_words[:100],
        "words": all_words,
        "needs_ocr": pages_needing_ocr > 0,
        "is_scanned": pages_needing_ocr == page_count,
    }



def _extract_from_docx(
    file_path: Path,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Extracts text, HEADINGS, ALIGNMENTS, and TABLES in exact order from DOCX.
    Preserves all tables as styled HTML tables and divider lines as <hr>.
    """
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    if progress_callback:
        progress_callback(30, "Reading Word document paragraphs, tables, and typography...")

    doc = docx.Document(str(file_path))
    elements_html = []
    all_text = []
    detected_fonts: Dict[str, int] = {}
    font_sizes: List[float] = []

    # Cascade to determine default DOCX font & size
    default_docx_font = None
    default_docx_size = None
    try:
        if "Normal" in doc.styles:
            normal_font = doc.styles["Normal"].font
            if normal_font and normal_font.name:
                default_docx_font = normal_font.name
            if normal_font and normal_font.size:
                default_docx_size = normal_font.size.pt

        if not default_docx_font:
            for rf in doc.styles.element.xpath("//w:docDefaults//w:rFonts"):
                ascii_val = rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
                hansi_val = rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi")
                if ascii_val:
                    default_docx_font = ascii_val
                    break
                elif hansi_val:
                    default_docx_font = hansi_val
                    break
                theme_val = rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}asciiTheme")
                if theme_val:
                    for rel in doc.part.rels.values():
                        if "theme" in rel.reltype:
                            import xml.etree.ElementTree as ET
                            t_root = ET.fromstring(rel.target_part.blob)
                            tag = "minorFont" if "minor" in theme_val.lower() else "majorFont"
                            for f_elem in t_root.iter():
                                if f_elem.tag.endswith(tag):
                                    for child in f_elem:
                                        if child.tag.endswith("latin") and "typeface" in child.attrib:
                                            default_docx_font = child.attrib["typeface"]
                                            break
                            break

        if not default_docx_size:
            for sz in doc.styles.element.xpath("//w:docDefaults//w:sz"):
                val = sz.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                if val and val.isdigit():
                    default_docx_size = float(val) / 2.0
                    break
    except Exception as e:
        logger.debug("Failed extracting docx typography defaults: %s", e)

    if not default_docx_font:
        default_docx_font = "Calibri"
    if not default_docx_size:
        default_docx_size = 11.0

    # Map alignments
    align_map = {
        WD_ALIGN_PARAGRAPH.CENTER: "center",
        WD_ALIGN_PARAGRAPH.RIGHT: "right",
        WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
        WD_ALIGN_PARAGRAPH.LEFT: "left",
    }

    def _extract_drawing_data_uri(d_elem) -> Optional[str]:
        import base64
        blips = d_elem.xpath(".//a:blip/@r:embed") or d_elem.xpath(".//@r:embed")
        if not blips:
            return None
        r_id = blips[0]
        if r_id in doc.part.rels:
            try:
                rel = doc.part.rels[r_id]
                target_part = rel.target_part
                content_type = getattr(target_part, "content_type", "image/png")
                blob = target_part.blob
                b64 = base64.b64encode(blob).decode("ascii")
                return f"data:{content_type};base64,{b64}"
            except Exception:
                return None
        return None

    def _render_drawing_icon(uri: str, descr: str = "icon") -> str:
        safe_descr = html.escape(descr, quote=True)
        return (
            f'<img src="{uri}" alt="{safe_descr}" class="docedit-docx-icon" '
            f'style="height: 1.1em; max-height: 18px; vertical-align: -0.15em; margin: 0 4px; display: inline-block;">'
        )

    def _format_docx_paragraph_runs(p_obj) -> str:
        # Collect anchored drawings in this paragraph, sorted by horizontal position posH
        anchors = []
        for d in p_obj._p.xpath(".//wp:anchor"):
            uri = _extract_drawing_data_uri(d)
            if uri:
                posH_nodes = d.xpath(".//wp:positionH/wp:posOffset/text()")
                posH = int(posH_nodes[0]) if (posH_nodes and posH_nodes[0].isdigit()) else 0
                descr_nodes = d.xpath(".//wp:docPr/@descr") or d.xpath(".//wp:docPr/@name")
                descr = descr_nodes[0] if descr_nodes else "icon"
                anchors.append({"posH": posH, "uri": uri, "descr": descr})
        anchors.sort(key=lambda x: x["posH"])

        # Extract items in document sequence
        items = []
        for child in p_obj._p:
            tag = child.tag.split("}")[-1]
            if tag == "hyperlink":
                r_id = child.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                target = doc.part.rels[r_id].target_ref if (r_id and r_id in doc.part.rels) else ""
                hl_text_pieces = []
                for sub_r in child.xpath(".//w:r"):
                    for sub in sub_r:
                        stag = sub.tag.split("}")[-1]
                        if stag == "t" and sub.text:
                            hl_text_pieces.append(sub.text)
                        elif stag == "tab":
                            hl_text_pieces.append("\t")
                        elif stag == "br":
                            hl_text_pieces.append("\n")
                if hl_text_pieces:
                    hl_txt = "".join(hl_text_pieces)
                    all_text.append(hl_txt)
                    items.append({
                        "type": "hyperlink",
                        "target": target,
                        "text": hl_txt,
                        "elem": child,
                    })
            elif tag == "r":
                # Check for inline drawings
                for idr in child.xpath(".//wp:inline"):
                    uri = _extract_drawing_data_uri(idr)
                    if uri:
                        descr_nodes = idr.xpath(".//wp:docPr/@descr") or idr.xpath(".//wp:docPr/@name")
                        descr = descr_nodes[0] if descr_nodes else "icon"
                        items.append({"type": "image", "uri": uri, "descr": descr, "elem": child})
                # Check text, tabs, line breaks
                run_text_pieces = []
                for sub in child:
                    stag = sub.tag.split("}")[-1]
                    if stag == "t" and sub.text:
                        run_text_pieces.append(sub.text)
                    elif stag == "tab":
                        run_text_pieces.append("\t")
                    elif stag == "br":
                        run_text_pieces.append("\n")
                if run_text_pieces:
                    full_t = "".join(run_text_pieces)
                    f_name = None
                    for rf in child.xpath(".//w:rFonts"):
                        f_name = rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii") or rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi")
                        if f_name:
                            break
                    if not f_name and p_obj.style and p_obj.style.font and p_obj.style.font.name:
                        f_name = p_obj.style.font.name
                    if not f_name:
                        f_name = default_docx_font
                    f_name = sanitize_font_name(f_name, default="Calibri")

                    f_size = None
                    for sz in child.xpath(".//w:sz"):
                        val = sz.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                        if val and val.isdigit():
                            f_size = float(val) / 2.0
                            break
                    if not f_size and p_obj.style and p_obj.style.font and p_obj.style.font.size:
                        f_size = p_obj.style.font.size.pt
                    if not f_size:
                        f_size = default_docx_size

                    if f_name:
                        detected_fonts[f_name] = detected_fonts.get(f_name, 0) + len(full_t)
                    if f_size:
                        font_sizes.append(f_size)

                    r_color = None
                    for wc in child.xpath(".//w:color"):
                        val = wc.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                        if val and re.match(r"^[0-9a-fA-F]{6}$", val) and val.lower() != "auto":
                            r_color = f"#{val.lower()}"
                            break

                    is_bold = bool(child.xpath(".//w:b"))
                    is_italic = bool(child.xpath(".//w:i"))
                    is_underline = bool(child.xpath(".//w:u"))

                    items.append({
                        "type": "run",
                        "text": full_t,
                        "bold": is_bold,
                        "italic": is_italic,
                        "underline": is_underline,
                        "font_name": f_name,
                        "font_size": f_size,
                        "color": r_color,
                        "elem": child,
                    })

        def _wrap_styled_span(txt_escaped, pt):
            if pt.get("bold"):
                txt_escaped = f"<strong>{txt_escaped}</strong>"
            if pt.get("italic"):
                txt_escaped = f"<em>{txt_escaped}</em>"
            if pt.get("underline"):
                txt_escaped = f"<u>{txt_escaped}</u>"
            run_styles = []
            fn = pt.get("font_name")
            if fn:
                safe_fn = html.escape(fn, quote=True)
                run_styles.append(f"font-family: '{safe_fn}';")
            fs = pt.get("font_size")
            if fs:
                run_styles.append(f"font-size: {fs}pt;")
            rc = pt.get("color")
            if rc:
                run_styles.append(f"color: {rc};")
            if run_styles:
                return f'<span style="{" ".join(run_styles)}">{txt_escaped}</span>'
            return txt_escaped

        # If anchored drawings exist, interleave them into whitespace gaps in posH order
        if anchors:
            expanded = []
            for it in items:
                if it["type"] == "run":
                    tokens = re.split(r'(\t+|\s{3,})', it["text"])
                    for tok in tokens:
                        if not tok:
                            continue
                        if re.match(r'^(\t+|\s{3,})$', tok):
                            expanded.append({"type": "gap", "text": tok, "elem": it["elem"]})
                        else:
                            sub_it = dict(it)
                            sub_it["text"] = tok
                            expanded.append(sub_it)
                else:
                    expanded.append(it)

            anc_idx = 0
            final_pieces = []
            for ep in expanded:
                if ep["type"] == "gap":
                    if anc_idx < len(anchors):
                        anc = anchors[anc_idx]
                        anc_idx += 1
                        final_pieces.append(_render_drawing_icon(anc["uri"], anc["descr"]) + " ")
                    else:
                        final_pieces.append("&emsp;&emsp;")
                elif ep["type"] == "hyperlink":
                    esc = html.escape(ep["text"])
                    tgt = html.escape(ep.get("target", ""))
                    final_pieces.append(f'<a href="{tgt}" style="color: inherit; text-decoration: underline;">{esc}</a>')
                elif ep["type"] == "run":
                    esc_t = html.escape(ep["text"]).replace("\t", "&emsp;&emsp;").replace("\n", "<br>")
                    final_pieces.append(_wrap_styled_span(esc_t, ep))
                elif ep["type"] == "image":
                    final_pieces.append(_render_drawing_icon(ep["uri"], ep["descr"]))

            while anc_idx < len(anchors):
                anc = anchors[anc_idx]
                anc_idx += 1
                final_pieces.insert(0, _render_drawing_icon(anc["uri"], anc["descr"]) + " ")

            return "".join(final_pieces)

        # Standard rendering without anchored drawings
        final_pieces = []
        for it in items:
            if it["type"] == "hyperlink":
                esc = html.escape(it["text"])
                tgt = html.escape(it.get("target", ""))
                final_pieces.append(f'<a href="{tgt}" style="color: inherit; text-decoration: underline;">{esc}</a>')
            elif it["type"] == "run":
                esc_t = html.escape(it["text"]).replace("\t", "&emsp;&emsp;").replace("\n", "<br>")
                final_pieces.append(_wrap_styled_span(esc_t, it))
            elif it["type"] == "image":
                final_pieces.append(_render_drawing_icon(it["uri"], it["descr"]))

        return "".join(final_pieces)

    current_list_items = []

    def _flush_list():
        if current_list_items:
            elements_html.append(f'<ul style="margin: 2pt 0 4pt 0; padding-left: 18pt;">\n' + "\n".join(current_list_items) + "\n</ul>")
            current_list_items.clear()

    # Iterate paragraphs AND tables in exact document sequence
    for item in doc.iter_inner_content():
        if isinstance(item, docx.text.paragraph.Paragraph):
            p = item
            txt = p.text
            has_drawings = bool(p._p.xpath(".//w:drawing"))
            if not txt.strip() and not has_drawings:
                continue
            all_text.append(txt)

            # Determine alignment
            align_css = ""
            if p.alignment and p.alignment in align_map and align_map[p.alignment] != "left":
                align_css = f'text-align: {align_map[p.alignment]};'

            content = _format_docx_paragraph_runs(p)
            if content:
                style_name = p.style.name.lower() if p.style else ""
                has_numpr = bool(p._p.xpath(".//w:numPr"))
                is_list = ("list" in style_name) or has_numpr

                p_styles = []
                if align_css:
                    p_styles.append(align_css.rstrip(";"))
                if p.style and p.style.font and p.style.font.name:
                    safe_pfn = html.escape(sanitize_font_name(p.style.font.name, default="Calibri"), quote=True)
                    p_styles.append(f"font-family: '{safe_pfn}'")
                style_attr = f' style="{"; ".join(p_styles)};"' if p_styles else ""

                if is_list:
                    current_list_items.append(f'<li{style_attr} style="margin: 1.5pt 0;">{content}</li>')
                else:
                    _flush_list()
                    if "heading 1" in style_name or "title" in style_name or bool(re.search(r'font-size:\s*(?:1[6-9]|[2-9]\d)\.?\d*pt', content)):
                        elements_html.append(f"<h1{style_attr}>{content}</h1>")
                    elif "heading 2" in style_name:
                        elements_html.append(f"<h2{style_attr}>{content}</h2>")
                    elif "heading 3" in style_name:
                        elements_html.append(f"<h3{style_attr}>{content}</h3>")
                    elif any(txt.strip().lower() == h.lower() for h in ["Personal Profile", "Work experience", "Education", "Reference(s)"]):
                        elements_html.append(f"<h2{style_attr}>{content}</h2>")
                    else:
                        elements_html.append(f"<p{style_attr}>{content}</p>")

        elif isinstance(item, docx.table.Table):
            _flush_list()
            # Extract Full Table preserving runs, formatting, and colors
            table = item
            tbl_rows_html = []
            for r_idx, row in enumerate(table.rows):
                is_header = (r_idx == 0)
                cell_tag = "th" if is_header else "td"
                cell_style = "border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);" if is_header else "border: 1px solid #777; padding: 6px 10px;"
                row_cells_html = []
                for cell in row.cells:
                    cell_p_html = []
                    for cp in cell.paragraphs:
                        cp_text = cp.text.strip()
                        if cp_text:
                            all_text.append(cp_text)
                        rendered_cp = _format_docx_paragraph_runs(cp)
                        if rendered_cp:
                            cell_p_html.append(rendered_cp)
                    cell_inner = "<br>".join(cell_p_html) if cell_p_html else html.escape(cell.text.strip())
                    row_cells_html.append(f'<{cell_tag} style="{cell_style}">{cell_inner}</{cell_tag}>')
                tbl_rows_html.append(f'<tr>{"".join(row_cells_html)}</tr>')

            full_tbl_html = (
                '<table class="docedit-table" style="border-collapse: collapse; width: 100%; margin: 1.2rem 0; border: 1px solid #777;">\n'
                + "\n".join(tbl_rows_html)
                + "\n</table>"
            )
            elements_html.append(full_tbl_html)

    _flush_list()
    full_text = "\n\n".join(all_text)
    combined_html = sanitize_document_html("\n".join(elements_html))

    if detected_fonts:
        dominant_font = max(detected_fonts.items(), key=lambda x: x[1])[0]
    else:
        dominant_font = default_docx_font or "Calibri"

    docx_font_res = resolve_font_with_fallback(dominant_font)
    all_fonts_css = generate_document_all_fonts_css([docx_font_res])
    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else default_docx_size

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": docx_font_res["used"],
        "font_size_pt": avg_size,
        "all_fonts_css": all_fonts_css,
        "stats": {
            "page_count": 1,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
            "fuzzy_word_count": 0,
        },
        "fuzzy_words": [],
        "needs_ocr": False,
        "is_scanned": False,
    }


def _extract_from_text(
    file_path: Path,
    kind: str = "text",
    progress_callback=None
) -> Dict[str, Any]:
    """Reads plain text, markdown, or HTML, preserving markdown tables and rules."""
    if progress_callback:
        progress_callback(40, "Loading document content...")

    content = ""
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            content = file_path.read_text(encoding=enc)
            break
        except Exception:
            pass

    if kind == "html":
        clean = re.sub(r"<script.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        body_match = re.search(r"<body[^>]*>(.*?)</body>", clean, flags=re.DOTALL | re.IGNORECASE)
        html_out = body_match.group(1) if body_match else clean
        plain_text = re.sub(r"<[^>]+>", " ", clean)
    elif kind == "markdown":
        # Convert markdown tables, rules, and headers to HTML
        lines = content.split("\n")
        parsed_elements = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Markdown table detection
            if "|" in line and i + 1 < len(lines) and re.match(r"^\|?\s*[-:]+[-| :]*\s*\|?$", lines[i + 1].strip()):
                table_lines = [line]
                i += 2  # Skip separator line
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i].strip())
                    i += 1

                tbl_html = ['<table class="docedit-table" style="border-collapse: collapse; width: 100%; margin: 1.2rem 0; border: 1px solid #777;">']
                for r_idx, t_row in enumerate(table_lines):
                    is_h = (r_idx == 0)
                    cells = [c.strip() for c in t_row.strip("|").split("|")]
                    c_tag = "th" if is_h else "td"
                    c_style = "border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);" if is_h else "border: 1px solid #777; padding: 6px 10px;"
                    cells_h = "".join(f'<{c_tag} style="{c_style}">{html.escape(c)}</{c_tag}>' for c in cells)
                    tbl_html.append(f'<tr>{cells_h}</tr>')
                tbl_html.append('</table>')
                parsed_elements.append("\n".join(tbl_html))
                continue

            # Horizontal rule
            if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", line):
                parsed_elements.append('<hr class="docedit-line" style="border: none; border-top: 1px solid #777; margin: 1.5rem 0;">')
            elif line.startswith("# "):
                parsed_elements.append(f"<h1>{html.escape(line[2:])}</h1>")
            elif line.startswith("## "):
                parsed_elements.append(f"<h2>{html.escape(line[3:])}</h2>")
            elif line.startswith("### "):
                parsed_elements.append(f"<h3>{html.escape(line[4:])}</h3>")
            elif line:
                parsed_elements.append(f"<p>{html.escape(line)}</p>")
            i += 1
        html_out = "\n".join(parsed_elements)
        plain_text = content
    else:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        html_paras = []
        for p in paragraphs:
            esc = html.escape(p).replace("\n", "<br>")
            html_paras.append(f"<p>{esc}</p>")
        html_out = "\n".join(html_paras)
        plain_text = content

    html_out = sanitize_document_html(html_out)

    matched_font = detect_visual_font_for_scanned_book(plain_text)

    return {
        "html": html_out,
        "raw_text": plain_text,
        "detected_font_name": matched_font,
        "font_size_pt": 12.0,
        "stats": {
            "page_count": 1,
            "word_count": len(plain_text.split()),
            "char_count": len(plain_text),
            "fuzzy_word_count": 0,
        },
        "fuzzy_words": [],
        "needs_ocr": False,
        "is_scanned": False,
    }
