"""
PDF document extraction pipeline preserving layout, tables, lines, and formatting.

Extracts text, tables via find_tables(), horizontal vector lines via get_drawings(),
embedded fonts, and runs aged-book OCR on scanned PDF pages.
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
    Main PDF extraction dispatcher preserving tables, lines, and layout.
    Preserves separate pages, exact layout geometry, background drawings/tables,
    and extracts in-place text blocks. Sanitizes all extracted HTML with an allowlist.
    """
    ext = file_path.suffix.lstrip(".").lower()
    kind = EXTENSION_KINDS.get(ext, "unknown")
    if kind != "pdf":
        raise ValueError(f"Unsupported document format '.{ext}'. DocEdit supports PDF files only.")

    if progress_callback:
        progress_callback(10, f"Analyzing {ext.upper()} document structure...")

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

    if res and res.get("html"):
        res["html"] = sanitize_document_html(res["html"])

    return res


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

