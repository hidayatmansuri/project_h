"""
Document exporters.

Writes edited document content preserving all layout, formatting, tables, lines,
and typography to the user's choice of output format:
- PDF: generated with embedded matching font, tables, borders, and lines via PyMuPDF Story.
- Word DOCX: generated with python-docx preserving native tables, header shading, borders, lines, alignments, and typography.
- Images (PNG, JPG, TIFF, BMP, WEBP): rendered via PyMuPDF with matching font, tables, and rules.
- Markdown: exported with markdown tables, divider rules, and headers.
- HTML: exported with clean embedded responsive CSS for tables, lines, and typography.
- Plain text: formatted with ASCII tables, divider lines, and text structure.
"""
import html
import io
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .conf import EXTENSION_KINDS, conf

logger = logging.getLogger(__name__)


class DocumentHtmlBlockParser(HTMLParser):
    """
    Parses editor HTML into structured block elements preserving exact order:
    - headings (h1, h2, h3)
    - paragraphs (p)
    - divider lines / rules (hr)
    - tables (table with rows, cells, and headers)
    - list items (li)
    """
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.in_table = False
        self.table_rows = []
        self.current_row = []
        self.current_cell_tag = None
        self.current_block_tag = None
        self.current_block_attrs = {}
        self.text_buf = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        attrs_dict = dict(attrs)

        if t == "table":
            self._flush_block()
            self.in_table = True
            self.table_rows = []
        elif self.in_table:
            if t == "tr":
                self.current_row = []
            elif t in ("td", "th"):
                self.current_cell_tag = t
                self.text_buf = []
            elif t in ("b", "strong"):
                self.text_buf.append("<strong>")
            elif t in ("i", "em"):
                self.text_buf.append("<em>")
            elif t == "u":
                self.text_buf.append("<u>")
            elif t == "br":
                self.text_buf.append("<br/>")
        elif t in ("h1", "h2", "h3", "p", "li", "blockquote"):
            self._flush_block()
            self.current_block_tag = t
            self.current_block_attrs = attrs_dict
            self.text_buf = []
        elif t == "hr":
            self._flush_block()
            self.blocks.append({"type": "hr"})
        elif t in ("b", "strong"):
            self.text_buf.append("<strong>")
        elif t in ("i", "em"):
            self.text_buf.append("<em>")
        elif t == "u":
            self.text_buf.append("<u>")
        elif t == "br":
            self.text_buf.append("<br/>")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "table":
            self.in_table = False
            if self.table_rows:
                self.blocks.append({"type": "table", "rows": self.table_rows})
            self.table_rows = []
        elif self.in_table:
            if t in ("td", "th"):
                cell_html = "".join(self.text_buf).strip()
                is_hdr = (self.current_cell_tag == "th")
                self.current_row.append({"is_header": is_hdr, "html": cell_html})
                self.text_buf = []
                self.current_cell_tag = None
            elif t == "tr":
                if self.current_row:
                    self.table_rows.append(self.current_row)
                    self.current_row = []
            elif t in ("b", "strong"):
                self.text_buf.append("</strong>")
            elif t in ("i", "em"):
                self.text_buf.append("</em>")
            elif t == "u":
                self.text_buf.append("</u>")
        elif t in ("h1", "h2", "h3", "p", "li", "blockquote"):
            self._flush_block()
        elif t in ("b", "strong"):
            self.text_buf.append("</strong>")
        elif t in ("i", "em"):
            self.text_buf.append("</em>")
        elif t == "u":
            self.text_buf.append("</u>")

    def handle_data(self, data):
        self.text_buf.append(data)

    def _flush_block(self):
        if self.current_block_tag:
            content = "".join(self.text_buf).strip()
            if content:
                style_str = self.current_block_attrs.get("style", "").lower()
                align = None
                if "text-align: center" in style_str:
                    align = "center"
                elif "text-align: right" in style_str:
                    align = "right"
                elif "text-align: justify" in style_str:
                    align = "justify"
                elif "text-align: left" in style_str:
                    align = "left"

                self.blocks.append({
                    "type": self.current_block_tag,
                    "html": content,
                    "align": align,
                })
            self.current_block_tag = None
            self.current_block_attrs = {}
            self.text_buf = []

    def close(self):
        super().close()
        self._flush_block()


def parse_html_blocks(html_content: str) -> List[Dict[str, Any]]:
    """Strips editor artifacts and parses HTML into structured block elements."""
    # Clean fuzzy highlights
    clean_html = re.sub(r'<span[^>]*class="[^"]*docedit-fuzzy[^"]*"[^>]*>(.*?)</span>', r'\1', html_content)
    clean_html = re.sub(r'data-[a-zA-Z0-9_\-]+="[^"]*"', '', clean_html)
    parser = DocumentHtmlBlockParser()
    parser.feed(clean_html)
    parser.close()
    return parser.blocks


def _write_pdf_layout_preserved(
    pages_data: List[Dict[str, Any]],
    original_file_path: Optional[Path],
    output_path: Path,
    font_name: str,
    font_path: Optional[str],
    font_size_pt: float,
    work_dir: Optional[Path] = None,
) -> Path:
    """
    Exports PDF while preserving 100% of the original document layout, tables,
    vector lines, borders, and graphics. Applies in-place redaction and text insertion
    only to modified text blocks.
    """
    import pymupdf

    # Try modifying original PDF directly if available
    if original_file_path and original_file_path.is_file() and original_file_path.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(str(original_file_path))
            for p_info in pages_data:
                p_num = p_info.get("page_num", 1)
                if 0 <= p_num - 1 < len(doc):
                    page = doc[p_num - 1]
                    for b in p_info.get("blocks", []):
                        if b.get("is_modified", False):
                            bbox = b.get("bbox")
                            if bbox and len(bbox) == 4:
                                rect = pymupdf.Rect(bbox)
                                page.add_redact_annot(rect, fill=(1, 1, 1))
                                page.apply_redactions()
                                y_pos = rect.y1 - max(2.0, rect.height * 0.15)
                                f_size = b.get("font_size_pt", font_size_pt)
                                font_kw = {"fontfile": font_path} if (font_path and Path(font_path).is_file()) else {"fontname": "helv"}
                                page.insert_text(pymupdf.Point(rect.x0, y_pos), b.get("text", ""), fontsize=f_size, **font_kw)
            doc.save(str(output_path))
            doc.close()
            return output_path
        except Exception as e:
            logger.warning("Failed direct PDF redaction, falling back to image compilation: %s", e)

    # Fallback: compile page background images with edited text overlay
    doc = pymupdf.open()
    for p_info in pages_data:
        p_num = p_info.get("page_num", 1)
        w = p_info.get("width", 595.0)
        h = p_info.get("height", 842.0)
        page = doc.new_page(width=w, height=h)

        # Place background image if available in work_dir
        if work_dir:
            img_p = work_dir / f"page_{p_num}.png"
            if img_p.is_file():
                page.insert_image(pymupdf.Rect(0, 0, w, h), filename=str(img_p))

        # Redact and insert modified blocks
        for b in p_info.get("blocks", []):
            if b.get("is_modified", False):
                bbox = b.get("bbox")
                if bbox and len(bbox) == 4:
                    rect = pymupdf.Rect(bbox)
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()
                    y_pos = rect.y1 - max(2.0, rect.height * 0.15)
                    f_size = b.get("font_size_pt", font_size_pt)
                    font_kw = {"fontfile": font_path} if (font_path and Path(font_path).is_file()) else {"fontname": "helv"}
                    page.insert_text(pymupdf.Point(rect.x0, y_pos), b.get("text", ""), fontsize=f_size, **font_kw)

    doc.save(str(output_path))
    doc.close()
    return output_path


def _write_image_layout_preserved(
    pages_data: List[Dict[str, Any]],
    work_dir: Optional[Path],
    output_path: Path,
    image_ext: str,
    font_name: str,
    font_path: Optional[str],
    font_size_pt: float,
) -> Path:
    """
    Renders edited text in-place directly onto the page images, preserving original
    page borders, tables, graphics, and background texture.
    """
    from PIL import Image, ImageDraw, ImageFont

    pil_font = None
    if font_path and Path(font_path).is_file():
        try:
            pil_font = ImageFont.truetype(str(font_path), size=int(font_size_pt * 2.5))
        except Exception:
            pil_font = None

    rendered_pages = []
    for p_info in pages_data:
        p_num = p_info.get("page_num", 1)
        base_img = None

        if work_dir:
            p_img_path = work_dir / f"page_{p_num}.png"
            if p_img_path.is_file():
                base_img = Image.open(str(p_img_path)).convert("RGB")

        if base_img is None:
            w = int(p_info.get("width", 800))
            h = int(p_info.get("height", 1100))
            base_img = Image.new("RGB", (w, h), (255, 255, 255))

        draw = ImageDraw.Draw(base_img)
        w_img, h_img = base_img.size
        p_w = p_info.get("width", w_img)
        p_h = p_info.get("height", h_img)
        scale_x = w_img / max(1.0, float(p_w))
        scale_y = h_img / max(1.0, float(p_h))

        for b in p_info.get("blocks", []):
            if b.get("is_modified", False):
                bbox = b.get("bbox")
                if bbox and len(bbox) == 4:
                    x0, y0, x1, y1 = bbox
                    ix0 = int(x0 * scale_x)
                    iy0 = int(y0 * scale_y)
                    ix1 = int(x1 * scale_x)
                    iy1 = int(y1 * scale_y)
                    # Mask old text with background
                    draw.rectangle([ix0, iy0, ix1, iy1], fill=(255, 255, 255))
                    b_size = int(b.get("font_size_pt", font_size_pt) * scale_y * 1.3)
                    cur_font = None
                    if font_path and Path(font_path).is_file():
                        try:
                            cur_font = ImageFont.truetype(str(font_path), size=max(10, b_size))
                        except Exception:
                            cur_font = pil_font
                    draw.text((ix0, iy0), b.get("text", ""), fill=(20, 20, 20), font=cur_font)

        rendered_pages.append(base_img)

    fmt_map = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "tif": "TIFF",
        "tiff": "TIFF",
        "bmp": "BMP",
        "webp": "WEBP",
    }
    save_fmt = fmt_map.get(image_ext.lower(), "PNG")

    if not rendered_pages:
        rendered_pages = [Image.new("RGB", (600, 800), (255, 255, 255))]

    if save_fmt == "TIFF" and len(rendered_pages) > 1:
        rendered_pages[0].save(
            str(output_path),
            format=save_fmt,
            save_all=True,
            append_images=rendered_pages[1:],
            dpi=(conf.OCR_DPI, conf.OCR_DPI)
        )
    else:
        rendered_pages[0].save(str(output_path), format=save_fmt, dpi=(conf.OCR_DPI, conf.OCR_DPI))

    return output_path


def write_document_to_disk(
    html_content: str,
    output_path: Path,
    extension: str,
    font_info: Dict[str, Any],
    pages_data: Optional[List[Dict[str, Any]]] = None,
    original_file_path: Optional[Path] = None,
    work_dir: Optional[Path] = None,
) -> Path:
    """
    Exports the edited document to output_path matching the chosen extension.
    If pages_data is present, exports in layout-preserved mode so tables, lines,
    borders, graphics, and separate pages are 100% maintained.
    """
    ext = extension.lstrip(".").lower()
    kind = EXTENSION_KINDS.get(ext, "text")

    font_name = font_info.get("name", "EB Garamond")
    font_path = font_info.get("font_path")
    font_size_pt = float(font_info.get("size_pt", 12.0))

    # If layout-preserved mode with pages_data
    if pages_data and len(pages_data) > 0:
        if kind == "pdf":
            return _write_pdf_layout_preserved(
                pages_data=pages_data,
                original_file_path=original_file_path,
                output_path=output_path,
                font_name=font_name,
                font_path=font_path,
                font_size_pt=font_size_pt,
                work_dir=work_dir,
            )
        elif kind == "image":
            return _write_image_layout_preserved(
                pages_data=pages_data,
                work_dir=work_dir,
                output_path=output_path,
                image_ext=ext,
                font_name=font_name,
                font_path=font_path,
                font_size_pt=font_size_pt,
            )

    if kind == "pdf":
        return _write_pdf(html_content, output_path, font_name, font_path, font_size_pt)
    elif kind == "image":
        return _write_image(html_content, output_path, ext, font_name, font_path, font_size_pt)
    elif kind == "docx":
        return _write_docx(html_content, output_path, font_name, font_size_pt)
    elif kind == "markdown":
        return _write_markdown(html_content, output_path)
    elif kind == "html":
        return _write_html(html_content, output_path, font_name, font_size_pt)
    else:  # Text default
        return _write_text(html_content, output_path)



def _prepare_clean_html_for_story(raw_html: str, font_name: str, font_size_pt: float) -> str:
    """
    Prepares HTML body for PyMuPDF Story rendering with full table and line CSS.
    """
    cleaned = re.sub(r'<span[^>]*class="[^"]*docedit-fuzzy[^"]*"[^>]*>(.*?)</span>', r'\1', raw_html)
    cleaned = re.sub(r'data-[a-zA-Z0-9_\-]+="[^"]*"', '', cleaned)
    body = f"""
    <div style="font-family: '{font_name}', serif; font-size: {font_size_pt}pt; line-height: 1.5; color: #111111;">
        {cleaned}
    </div>
    """
    return body


def _write_pdf(
    html_content: str,
    output_path: Path,
    font_name: str,
    font_path: Optional[str],
    font_size_pt: float
) -> Path:
    """Generates PDF using PyMuPDF Story with full table and vector line preservation."""
    import pymupdf

    story_html = _prepare_clean_html_for_story(html_content, font_name, font_size_pt)

    # Base styling for tables, lines, headings, and paragraphs
    base_css = f"""
    body, div {{
        font-family: '{font_name}', serif;
        font-size: {font_size_pt}pt;
        line-height: 1.45;
        color: #111111;
    }}
    table, .docedit-table {{
        border-collapse: collapse;
        width: 100%;
        margin: 12pt 0;
        border: 1pt solid #555555;
    }}
    th, td {{
        border: 1pt solid #666666;
        padding: 5pt 8pt;
        text-align: left;
        font-size: {max(8.0, font_size_pt - 1.5)}pt;
    }}
    th {{
        font-weight: bold;
        background-color: #ededed;
    }}
    hr, .docedit-line {{
        border: none;
        border-top: 1pt solid #666666;
        margin: 12pt 0;
    }}
    h1 {{ font-size: {font_size_pt + 6}pt; font-weight: bold; margin: 14pt 0 7pt 0; }}
    h2 {{ font-size: {font_size_pt + 4}pt; font-weight: bold; margin: 12pt 0 6pt 0; }}
    h3 {{ font-size: {font_size_pt + 2}pt; font-weight: bold; margin: 10pt 0 5pt 0; }}
    p {{ margin: 0 0 8pt 0; text-align: justify; }}
    """

    custom_css = base_css
    archive = None
    if font_path and Path(font_path).is_file():
        fp = Path(font_path)
        archive = pymupdf.Archive(str(fp.parent))
        custom_css += f"""
        @font-face {{
            font-family: '{font_name}';
            src: url('{fp.name}');
        }}
        """

    story = pymupdf.Story(story_html, user_css=custom_css, archive=archive)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page_rect = pymupdf.paper_rect("a4")
    margin = 54  # 0.75 in margins
    content_rect = page_rect + (margin, margin, -margin, -margin)

    more = 1
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(dev)
        writer.end_page()
    writer.close()

    output_path.write_bytes(buf.getvalue())
    return output_path


def _write_image(
    html_content: str,
    output_path: Path,
    image_ext: str,
    font_name: str,
    font_path: Optional[str],
    font_size_pt: float
) -> Path:
    """Renders the edited document with tables & lines to an image using PyMuPDF pixmap."""
    import pymupdf
    from PIL import Image

    pdf_tmp = output_path.with_suffix(".tmp.pdf")
    _write_pdf(html_content, pdf_tmp, font_name, font_path, font_size_pt)

    doc = pymupdf.open(str(pdf_tmp))
    if len(doc) == 0:
        pdf_tmp.unlink(missing_ok=True)
        return output_path

    fmt_map = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "tif": "TIFF",
        "tiff": "TIFF",
        "bmp": "BMP",
        "webp": "WEBP",
    }
    save_fmt = fmt_map.get(image_ext.lower(), "PNG")

    pix = doc[0].get_pixmap(dpi=conf.OCR_DPI)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    if save_fmt == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    if save_fmt == "TIFF" and len(doc) > 1:
        other_frames = []
        for p_idx in range(1, len(doc)):
            p_pix = doc[p_idx].get_pixmap(dpi=conf.OCR_DPI)
            p_img = Image.open(io.BytesIO(p_pix.tobytes("png")))
            other_frames.append(p_img)
        img.save(str(output_path), format=save_fmt, save_all=True, append_images=other_frames, dpi=(conf.OCR_DPI, conf.OCR_DPI))
    else:
        img.save(str(output_path), format=save_fmt, dpi=(conf.OCR_DPI, conf.OCR_DPI))

    doc.close()
    pdf_tmp.unlink(missing_ok=True)
    return output_path


def _write_docx(
    html_content: str,
    output_path: Path,
    font_name: str,
    font_size_pt: float
) -> Path:
    """
    Generates Word DOCX preserving full table structures, header shading,
    borders, divider lines, headings, alignments, and matching typography.
    """
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from docx.shared import Inches, Pt

    blocks = parse_html_blocks(html_content)

    doc = docx.Document()

    # Set normal style typography
    style = doc.styles["Normal"]
    font = style.font
    font.name = font_name
    font.size = Pt(font_size_pt)

    # 1-inch margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    align_map = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        "left": WD_ALIGN_PARAGRAPH.LEFT,
    }

    def add_formatted_runs(p, raw_text, base_size=font_size_pt):
        tokens = re.split(
            r'(<strong>.*?</strong>|<em>.*?</em>|<u>.*?</u>|<br\s*/?>)',
            raw_text,
            flags=re.DOTALL | re.IGNORECASE
        )
        for tok in tokens:
            if not tok:
                continue
            if re.match(r'<br\s*/?>', tok, flags=re.IGNORECASE):
                p.add_run('\n')
                continue

            bold = False
            italic = False
            underline = False
            txt = tok

            if tok.lower().startswith('<strong>') and tok.lower().endswith('</strong>'):
                bold = True
                txt = tok[8:-9]
            elif tok.lower().startswith('<em>') and tok.lower().endswith('</em>'):
                italic = True
                txt = tok[4:-5]
            elif tok.lower().startswith('<u>') and tok.lower().endswith('</u>'):
                underline = True
                txt = tok[3:-4]

            clean = html.unescape(re.sub(r'<[^>]+>', '', txt))
            if clean:
                r = p.add_run(clean)
                r.font.name = font_name
                r.font.size = Pt(base_size)
                r.bold = bold
                r.italic = italic
                r.underline = underline

    for block in blocks:
        b_type = block["type"]

        if b_type == "hr":
            # Native divider line in Word via border
            p_hr = doc.add_paragraph()
            p_hr.paragraph_format.space_before = Pt(8)
            p_hr.paragraph_format.space_after = Pt(8)
            pPr = p_hr._p.get_or_add_pPr()
            pBdr = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="8" w:space="1" w:color="777777"/></w:pBdr>')
            pPr.append(pBdr)

        elif b_type in ("h1", "h2", "h3"):
            level = int(b_type[1])
            p_h = doc.add_heading(level=level)
            align = block.get("align")
            if align in align_map:
                p_h.alignment = align_map[align]
            h_size = font_size_pt + (6 - level * 2)
            add_formatted_runs(p_h, block["html"], base_size=h_size)

        elif b_type == "table":
            rows = block["rows"]
            if not rows:
                continue
            col_count = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=col_count)
            table.style = "Table Grid"

            for r_idx, row in enumerate(rows):
                for c_idx, cell_data in enumerate(row):
                    if c_idx >= col_count:
                        break
                    cell = table.cell(r_idx, c_idx)
                    p_cell = cell.paragraphs[0]
                    p_cell.paragraph_format.space_after = Pt(2)
                    p_cell.paragraph_format.space_before = Pt(2)

                    is_hdr = cell_data.get("is_header", False)
                    if is_hdr:
                        shd = parse_xml(r'<w:shd {} w:fill="EAEAEA"/>'.format(nsdecls('w')))
                        cell._tc.get_or_add_tcPr().append(shd)

                    cell_html = cell_data.get("html", "")
                    if is_hdr:
                        cell_html = f"<strong>{cell_html}</strong>"
                    add_formatted_runs(p_cell, cell_html, base_size=max(9.0, font_size_pt - 1.5))

            # Add breathing room after table
            p_spacer = doc.add_paragraph()
            p_spacer.paragraph_format.space_before = Pt(4)
            p_spacer.paragraph_format.space_after = Pt(4)

        elif b_type == "li":
            p_li = doc.add_paragraph(style="List Bullet")
            add_formatted_runs(p_li, block["html"])

        else:  # Paragraph 'p' or blockquote
            p = doc.add_paragraph()
            align = block.get("align")
            if align in align_map:
                p.alignment = align_map[align]
            add_formatted_runs(p, block["html"])

    doc.save(str(output_path))
    return output_path


def _write_markdown(html_content: str, output_path: Path) -> Path:
    """Converts HTML blocks to clean markdown preserving tables and divider lines."""
    blocks = parse_html_blocks(html_content)
    md_lines = []

    for block in blocks:
        b_type = block["type"]
        if b_type == "hr":
            md_lines.append("\n---\n")
        elif b_type == "h1":
            text = html.unescape(re.sub(r'<[^>]+>', '', block["html"]))
            md_lines.append(f"# {text}\n")
        elif b_type == "h2":
            text = html.unescape(re.sub(r'<[^>]+>', '', block["html"]))
            md_lines.append(f"## {text}\n")
        elif b_type == "h3":
            text = html.unescape(re.sub(r'<[^>]+>', '', block["html"]))
            md_lines.append(f"### {text}\n")
        elif b_type == "li":
            text = html.unescape(re.sub(r'<[^>]+>', '', block["html"]))
            md_lines.append(f"- {text}")
        elif b_type == "table":
            rows = block["rows"]
            if not rows:
                continue
            col_count = max(len(r) for r in rows)
            table_md = []
            # Header row
            header_cells = [html.unescape(re.sub(r'<[^>]+>', '', cell.get("html", ""))) for cell in rows[0]]
            while len(header_cells) < col_count:
                header_cells.append("")
            table_md.append("| " + " | ".join(header_cells) + " |")
            table_md.append("| " + " | ".join(["---"] * col_count) + " |")

            for row in rows[1:]:
                cells = [html.unescape(re.sub(r'<[^>]+>', '', cell.get("html", ""))) for cell in row]
                while len(cells) < col_count:
                    cells.append("")
                table_md.append("| " + " | ".join(cells) + " |")

            md_lines.append("\n" + "\n".join(table_md) + "\n")
        else:  # Paragraph 'p'
            text = block["html"]
            text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.IGNORECASE)
            text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.IGNORECASE)
            text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
            clean = html.unescape(re.sub(r'<[^>]+>', '', text)).strip()
            if clean:
                md_lines.append(f"{clean}\n")

    output_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")
    return output_path


def _write_html(html_content: str, output_path: Path, font_name: str, font_size_pt: float) -> Path:
    """Wraps HTML in clean HTML5 document with embedded styling for tables, lines & typography."""
    cleaned = re.sub(r'<span[^>]*class="[^"]*docedit-fuzzy[^"]*"[^>]*>(.*?)</span>', r'\1', html_content)
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Edited Document</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={font_name.replace(' ', '+')}:wght@400;700&display=swap">
<style>
body {{
    font-family: '{font_name}', serif;
    font-size: {font_size_pt}pt;
    line-height: 1.6;
    color: #212529;
    max-width: 860px;
    margin: 2.5rem auto;
    padding: 0 1.5rem;
}}
table, .docedit-table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1.5rem 0;
    border: 1px solid #777777;
}}
th, td {{
    border: 1px solid #777777;
    padding: 8px 12px;
    text-align: left;
}}
th {{
    font-weight: bold;
    background-color: #f2f2f2;
}}
hr, .docedit-line {{
    border: none;
    border-top: 1px solid #777777;
    margin: 1.5rem 0;
}}
h1, h2, h3 {{ margin-top: 1.5rem; margin-bottom: 0.6rem; }}
p {{ margin-bottom: 1.2rem; text-align: justify; }}
</style>
</head>
<body>
{cleaned}
</body>
</html>
"""
    output_path.write_text(full_html, encoding="utf-8")
    return output_path


def _write_text(html_content: str, output_path: Path) -> Path:
    """Formats HTML to clean plain text with structured ASCII tables and divider rules."""
    blocks = parse_html_blocks(html_content)
    text_lines = []

    for block in blocks:
        b_type = block["type"]
        if b_type == "hr":
            text_lines.append("-" * 60)
        elif b_type in ("h1", "h2", "h3"):
            txt = html.unescape(re.sub(r'<[^>]+>', '', block["html"])).strip()
            text_lines.append(txt)
            text_lines.append("=" * min(len(txt), 60) if b_type == "h1" else "-" * min(len(txt), 60))
        elif b_type == "li":
            txt = html.unescape(re.sub(r'<[^>]+>', '', block["html"])).strip()
            text_lines.append(f"  * {txt}")
        elif b_type == "table":
            rows = block["rows"]
            if not rows:
                continue
            # Format as clean ASCII table
            table_matrix = []
            col_count = max(len(r) for r in rows)
            for row in rows:
                row_vals = [html.unescape(re.sub(r'<[^>]+>', '', c.get("html", ""))).strip() for c in row]
                while len(row_vals) < col_count:
                    row_vals.append("")
                table_matrix.append(row_vals)

            col_widths = [max(len(table_matrix[r][c]) for r in range(len(table_matrix))) for c in range(col_count)]
            col_widths = [max(w, 4) for w in col_widths]

            # Render rows
            for r_idx, row in enumerate(table_matrix):
                cells_str = [row[c].ljust(col_widths[c]) for c in range(col_count)]
                text_lines.append(" | ".join(cells_str))
                if r_idx == 0:
                    text_lines.append("-+-".join("-" * col_widths[c] for c in range(col_count)))
            text_lines.append("")
        else:  # Paragraph
            raw = re.sub(r'<br\s*/?>', '\n', block["html"], flags=re.IGNORECASE)
            txt = html.unescape(re.sub(r'<[^>]+>', '', raw)).strip()
            if txt:
                text_lines.append(txt)
                text_lines.append("")

    output_path.write_text("\n".join(text_lines).strip() + "\n", encoding="utf-8")
    return output_path
