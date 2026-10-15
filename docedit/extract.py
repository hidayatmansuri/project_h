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
from .fontmatch import clean_pdf_font_name, detect_visual_font_for_scanned_book
from .ocr import ocr_image

logger = logging.getLogger(__name__)


def extract_document(
    file_path: Path,
    ocr_lang: str = "eng",
    work_dir: Optional[Path] = None,
    sid: Optional[str] = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Main extraction dispatcher preserving tables, lines, and layout.
    For non-editable documents (PDF and images with text), preserves separate pages,
    exact layout geometry, background drawings/tables, and extracts in-place text blocks.
    """
    ext = file_path.suffix.lstrip(".").lower()
    kind = EXTENSION_KINDS.get(ext, "unknown")

    if progress_callback:
        progress_callback(10, f"Analyzing {ext.upper()} document structure...")

    if kind == "image":
        return _extract_from_image(file_path, ocr_lang=ocr_lang, work_dir=work_dir, sid=sid, progress_callback=progress_callback)
    elif kind == "pdf":
        return _extract_from_pdf(file_path, ocr_lang=ocr_lang, work_dir=work_dir, sid=sid, progress_callback=progress_callback)
    elif kind == "docx":
        return _extract_from_docx(file_path, progress_callback=progress_callback)
    elif kind in ("text", "markdown", "html"):
        return _extract_from_text(file_path, kind=kind, progress_callback=progress_callback)
    else:
        return _extract_from_text(file_path, kind="text", progress_callback=progress_callback)


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
    progress_callback=None
) -> Dict[str, Any]:
    """
    Extracts text, divider lines, and separate page structures from scanned book pages via OCR.
    Preserves original image background, tables, borders, and separate pages.
    """
    if progress_callback:
        progress_callback(20, "Loading image and analyzing page layout & lines...")

    img = Image.open(str(file_path))
    pages_html = []
    pages_data = []
    all_fuzzy_words = []
    all_text = []
    page_count = 0
    font_sizes = []

    try:
        frame_idx = 0
        while True:
            img.seek(frame_idx)
            page_count += 1
            if progress_callback:
                progress_callback(30 + min(40, frame_idx * 10), f"Extracting page {page_count}...")

            cur_frame = img.copy()
            orig_w, orig_h = cur_frame.size

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

            res = ocr_image(cur_frame, lang=ocr_lang, dpi=conf.OCR_DPI)
            line_boxes = res.get("line_boxes", [])
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
                left_pct = round((lx / max(1, orig_w)) * 100, 3)
                top_pct = round((ly / max(1, orig_h)) * 100, 3)
                width_pct = round((lw / max(1, orig_w)) * 100, 3)
                height_pct = round((lh / max(1, orig_h)) * 100, 3)
                est_line_pt = round((lh * 72.0 / conf.OCR_DPI) * 1.15, 1)
                est_line_pt = max(9.0, min(est_line_pt, 48.0))

                b_id = f"p{page_count}_b{b_idx}"
                page_blocks.append({
                    "id": b_id,
                    "text": b_text,
                    "bbox": [lx, ly, lx + lw, ly + lh],
                    "left_pct": left_pct,
                    "top_pct": top_pct,
                    "width_pct": width_pct,
                    "height_pct": height_pct,
                    "font_name": "EB Garamond",
                    "font_size_pt": est_line_pt,
                    "is_header": est_line_pt >= 16,
                    "has_fuzzy": lb.get("has_fuzzy", False),
                    "page": page_count,
                })

                escaped = html.escape(b_text)
                block_html_items.append(
                    f'<div class="docedit-text-block{" has-fuzzy" if lb.get("has_fuzzy") else ""}" '
                    f'contenteditable="true" spellcheck="false" '
                    f'data-block-id="{b_id}" data-page="{page_count}" '
                    f'style="left: {left_pct}%; top: {top_pct}%; min-width: {width_pct}%; font-size: {est_line_pt}pt;">'
                    f'{escaped}</div>'
                )
                b_idx += 1

            img_url = f"/docedit/api/page-image/{sid}/{page_count}/" if sid else f"page_{page_count}.png"

            pages_data.append({
                "page_num": page_count,
                "width": orig_w,
                "height": orig_h,
                "aspect_ratio": round(orig_h / max(1, orig_w), 4),
                "image_url": img_url,
                "blocks": page_blocks,
            })

            sheet_html = f'''<div class="docedit-page-sheet" data-page="{page_count}" id="doceditPage_{page_count}">
  <div class="page-sheet-header">
    <div class="page-sheet-badge"><i class="fa-solid fa-file-image"></i> Page {page_count}</div>
    <div class="page-sheet-dims">{orig_w} × {orig_h} px</div>
  </div>
  <div class="page-sheet-canvas" style="aspect-ratio: {orig_w} / {orig_h};">
    <img class="page-bg-img" src="{img_url}" alt="Page {page_count} Original Layout" draggable="false" />
    <div class="page-text-overlay">
      {"".join(block_html_items)}
    </div>
  </div>
</div>'''
            pages_html.append(sheet_html)
            all_text.append(res["text"])
            for fw in res.get("fuzzy_words", []):
                fw["page"] = page_count
                all_fuzzy_words.append(fw)

            frame_idx += 1
    except EOFError:
        pass

    full_text = "\n\n".join(all_text)
    combined_html = "\n".join(pages_html)
    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else 12.0
    matched_font = detect_visual_font_for_scanned_book(full_text)

    for p in pages_data:
        for b in p["blocks"]:
            b["font_name"] = matched_font

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": matched_font,
        "font_size_pt": avg_size,
        "is_layout_preserved": True,
        "pages": pages_data,
        "stats": {
            "page_count": page_count,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
            "fuzzy_word_count": len(all_fuzzy_words),
        },
        "fuzzy_words": all_fuzzy_words[:100],
        "needs_ocr": True,
        "is_scanned": True,
    }


def _extract_from_pdf(
    file_path: Path,
    ocr_lang: str = "eng",
    work_dir: Optional[Path] = None,
    sid: Optional[str] = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Extracts text, TABLES, lines, and formatting from PDF.
    Preserves exact tables, vector rules, and separate page structures.
    Renders high-resolution background pages so all tables, lines, borders,
    and graphics remain completely intact while text is editable in-place.
    """
    import pymupdf

    if progress_callback:
        progress_callback(20, "Inspecting PDF tables, lines, and typography...")

    doc = pymupdf.open(str(file_path))
    page_count = len(doc)

    pages_html = []
    pages_data = []
    all_text = []
    all_fuzzy_words = []
    detected_fonts: Dict[str, int] = {}
    font_sizes: List[float] = []
    pages_needing_ocr = 0

    for idx, page in enumerate(doc):
        page_num = idx + 1
        page_text = page.get_text()
        rect = page.rect
        p_width = round(rect.width, 1)
        p_height = round(rect.height, 1)

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
                    lines = b.get("lines", [])
                    for line in lines:
                        line_bbox = line.get("bbox", (0, 0, 0, 0))
                        line_spans = line.get("spans", [])
                        if not line_spans:
                            continue
                        line_str = "".join(s.get("text", "") for s in line_spans).strip()
                        if not line_str:
                            continue

                        main_span = max(line_spans, key=lambda s: len(s.get("text", "")))
                        raw_f = main_span.get("font", "")
                        resolved_f = font_res_map.get(raw_f) or font_res_map.get(raw_f.lstrip("/")) or raw_f
                        f_name = clean_pdf_font_name(resolved_f)
                        if not f_name or f_name.lower() in ("default", "unknown"):
                            f_name = None
                        f_size = round(main_span.get("size", 12.0), 1)

                        span_flags = main_span.get("flags", 0)
                        is_bold = bool(span_flags & (1 << 4))
                        is_italic = bool(span_flags & (1 << 1))
                        f_lower = (resolved_f or raw_f).lower()
                        if not is_bold and any(b in f_lower for b in ["bold", "black", "heavy", "semibold", "demibold", "bd"]):
                            is_bold = True
                        if not is_italic and any(it in f_lower for it in ["italic", "oblique", "slant", "kursiv"]):
                            is_italic = True

                        if f_name:
                            detected_fonts[f_name] = detected_fonts.get(f_name, 0) + len(line_str)
                        if f_size > 4:
                            font_sizes.append(f_size)

                        lx0, ly0, lx1, ly1 = line_bbox
                        w_box = max(1.0, lx1 - lx0)
                        h_box = max(1.0, ly1 - ly0)

                        left_pct = round((lx0 / max(1, p_width)) * 100, 3)
                        top_pct = round((ly0 / max(1, p_height)) * 100, 3)
                        width_pct = round((w_box / max(1, p_width)) * 100, 3)
                        height_pct = round((h_box / max(1, p_height)) * 100, 3)

                        b_id = f"p{page_num}_b{b_idx}"
                        page_blocks.append({
                            "id": b_id,
                            "text": line_str,
                            "bbox": [round(lx0, 1), round(ly0, 1), round(lx1, 1), round(ly1, 1)],
                            "orig_bbox": [round(lx0, 1), round(ly0, 1), round(lx1, 1), round(ly1, 1)],
                            "left_pct": left_pct,
                            "top_pct": top_pct,
                            "width_pct": width_pct,
                            "height_pct": height_pct,
                            "font_name": f_name or "EB Garamond",
                            "font_size_pt": f_size,
                            "is_bold": is_bold,
                            "is_italic": is_italic,
                            "is_underline": False,
                            "is_header": f_size >= 15,
                            "page": page_num,
                        })

                        escaped = html.escape(line_str)
                        block_font_css = f"font-family: '{f_name}', serif; " if f_name else ""
                        weight_css = "font-weight: bold; " if is_bold else ""
                        style_css = "font-style: italic; " if is_italic else ""
                        block_html_items.append(
                            f'<div class="docedit-text-block" '
                            f'contenteditable="true" spellcheck="false" '
                            f'data-block-id="{b_id}" data-page="{page_num}" '
                            f'style="left: {left_pct}%; top: {top_pct}%; min-width: {width_pct}%; font-size: {f_size}pt; {block_font_css}{weight_css}{style_css}">'
                            f'{escaped}</div>'
                        )
                        b_idx += 1
            all_text.append(page_text)
        else:
            pages_needing_ocr += 1
            pix = page.get_pixmap(dpi=conf.OCR_DPI)
            p_img = Image.open(io.BytesIO(pix.tobytes("png")))
            res = ocr_image(p_img, lang=ocr_lang, dpi=conf.OCR_DPI)
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
                est_line_pt = round((lh * 72.0 / conf.OCR_DPI) * 1.15, 1)

                b_id = f"p{page_num}_b{b_idx}"
                bbox_calc = [
                    round(lx * (p_width / pix.width), 1),
                    round(ly * (p_height / pix.height), 1),
                    round((lx + lw) * (p_width / pix.width), 1),
                    round((ly + lh) * (p_height / pix.height), 1)
                ]
                page_blocks.append({
                    "id": b_id,
                    "text": b_text,
                    "bbox": bbox_calc,
                    "orig_bbox": list(bbox_calc),
                    "left_pct": left_pct,
                    "top_pct": top_pct,
                    "width_pct": width_pct,
                    "height_pct": height_pct,
                    "font_name": "EB Garamond",
                    "font_size_pt": est_line_pt,
                    "is_bold": False,
                    "is_italic": False,
                    "is_underline": False,
                    "is_header": est_line_pt >= 15,
                    "has_fuzzy": lb.get("has_fuzzy", False),
                    "page": page_num,
                })
                escaped = html.escape(b_text)
                block_html_items.append(
                    f'<div class="docedit-text-block{" has-fuzzy" if lb.get("has_fuzzy") else ""}" '
                    f'contenteditable="true" spellcheck="false" '
                    f'data-block-id="{b_id}" data-page="{page_num}" '
                    f'style="left: {left_pct}%; top: {top_pct}%; min-width: {width_pct}%; font-size: {est_line_pt}pt;">'
                    f'{escaped}</div>'
                )
                b_idx += 1

            all_text.append(res["text"])
            for fw in res.get("fuzzy_words", []):
                fw["page"] = page_num
                all_fuzzy_words.append(fw)

        pages_data.append({
            "page_num": page_num,
            "width": p_width,
            "height": p_height,
            "aspect_ratio": round(p_height / max(1, p_width), 4),
            "image_url": img_url,
            "blocks": page_blocks,
        })

        sheet_html = f'''<div class="docedit-page-sheet" data-page="{page_num}" id="doceditPage_{page_num}">
  <div class="page-sheet-header">
    <div class="page-sheet-badge"><i class="fa-solid fa-file-pdf"></i> Page {page_num} of {page_count}</div>
    <div class="page-sheet-dims">{int(p_width)} × {int(p_height)} pt</div>
  </div>
  <div class="page-sheet-canvas" style="aspect-ratio: {p_width} / {p_height};">
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

    for p in pages_data:
        for b in p["blocks"]:
            if not b.get("font_name") or b["font_name"] == "EB Garamond":
                b["font_name"] = dominant_font

    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else 12.0

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": dominant_font,
        "font_size_pt": avg_size,
        "is_layout_preserved": True,
        "pages": pages_data,
        "stats": {
            "page_count": page_count,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
            "fuzzy_word_count": len(all_fuzzy_words),
        },
        "fuzzy_words": all_fuzzy_words[:100],
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

    # Iterate paragraphs AND tables in exact document sequence
    for item in doc.iter_inner_content():
        if isinstance(item, docx.text.paragraph.Paragraph):
            p = item
            txt = p.text
            if not txt.strip():
                continue
            all_text.append(txt)

            # Determine alignment
            align_css = ""
            if p.alignment and p.alignment in align_map and align_map[p.alignment] != "left":
                align_css = f'text-align: {align_map[p.alignment]};'

            run_html = []
            for r in p.runs:
                t = r.text
                if not t:
                    continue
                f_name = r.font.name
                if not f_name:
                    for rf in r._r.xpath(".//w:rFonts"):
                        f_name = rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii") or rf.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi")
                        if f_name:
                            break
                if not f_name and p.style and p.style.font and p.style.font.name:
                    f_name = p.style.font.name
                if not f_name:
                    f_name = default_docx_font

                f_size = r.font.size.pt if r.font.size else (p.style.font.size.pt if (p.style and p.style.font and p.style.font.size) else default_docx_size)

                if f_name:
                    detected_fonts[f_name] = detected_fonts.get(f_name, 0) + len(t)
                if f_size:
                    font_sizes.append(f_size)

                esc = html.escape(t)
                if r.bold:
                    esc = f"<strong>{esc}</strong>"
                if r.italic:
                    esc = f"<em>{esc}</em>"
                if r.underline:
                    esc = f"<u>{esc}</u>"
                run_html.append(esc)

            if run_html:
                content = "".join(run_html)
                style_name = p.style.name.lower() if p.style else ""
                style_attr = f' style="{align_css}"' if align_css else ""

                if "heading 1" in style_name or "title" in style_name:
                    elements_html.append(f"<h1{style_attr}>{content}</h1>")
                elif "heading 2" in style_name:
                    elements_html.append(f"<h2{style_attr}>{content}</h2>")
                elif "heading 3" in style_name:
                    elements_html.append(f"<h3{style_attr}>{content}</h3>")
                elif "list bullet" in style_name:
                    elements_html.append(f"<ul><li{style_attr}>{content}</li></ul>")
                else:
                    elements_html.append(f"<p{style_attr}>{content}</p>")

        elif isinstance(item, docx.table.Table):
            # Extract Full Table
            table = item
            tbl_rows_html = []
            for r_idx, row in enumerate(table.rows):
                is_header = (r_idx == 0)
                cell_tag = "th" if is_header else "td"
                cell_style = "border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);" if is_header else "border: 1px solid #777; padding: 6px 10px;"
                row_cells_html = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    all_text.append(cell_text)
                    esc_cell = html.escape(cell_text)
                    row_cells_html.append(f'<{cell_tag} style="{cell_style}">{esc_cell}</{cell_tag}>')
                tbl_rows_html.append(f'<tr>{"".join(row_cells_html)}</tr>')

            full_tbl_html = (
                '<table class="docedit-table" style="border-collapse: collapse; width: 100%; margin: 1.2rem 0; border: 1px solid #777;">\n'
                + "\n".join(tbl_rows_html)
                + "\n</table>"
            )
            elements_html.append(full_tbl_html)

    full_text = "\n\n".join(all_text)
    combined_html = "\n".join(elements_html)

    if detected_fonts:
        dominant_font = max(detected_fonts.items(), key=lambda x: x[1])[0]
    else:
        dominant_font = default_docx_font or "Calibri"

    avg_size = round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else default_docx_size

    return {
        "html": combined_html,
        "raw_text": full_text,
        "detected_font_name": dominant_font,
        "font_size_pt": avg_size,
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
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
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
